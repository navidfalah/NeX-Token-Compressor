package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"regexp"
	"time"
)

// Provider configuration
var (
	DeepSeekAPIKey = os.Getenv("DEEPSEEK_API_KEY")
	GeminiAPIKey   = os.Getenv("GEMINI_API_KEY")
)

func init() {
	if DeepSeekAPIKey == "" {
		DeepSeekAPIKey = "sk-d25091a148a04c1aa3eeabaffebda4c0" // Fallback MVP key
	}
	if GeminiAPIKey == "" {
		GeminiAPIKey = "AIzaSyCVwClfpS71NkDCsH_0FeU0tusQpP2bwMo" // Fallback MVP key
	}
}

// Structs for parsing incoming OpenAI-like requests
type ChatMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type ChatRequest struct {
	Model       string        `json:"model"`
	Messages    []ChatMessage `json:"messages"`
	Temperature float64       `json:"temperature,omitempty"`
}

type OpenAIResponse struct {
	Id      string `json:"id"`
	Object  string `json:"object"`
	Created int64  `json:"created"`
	Model   string `json:"model"`
	Choices []struct {
		Message ChatMessage `json:"message"`
	} `json:"choices"`
	Usage struct {
		PromptTokens     int `json:"prompt_tokens"`
		CompletionTokens int `json:"completion_tokens"`
		TotalTokens      int `json:"total_tokens"`
	} `json:"usage"`
}

// -----------------------------------------------------------------------------
// Core Routing Heuristics
// -----------------------------------------------------------------------------
func shouldRouteToGemini(req *ChatRequest) bool {
	// Complexity Threshold 1: Total prompt length
	totalLength := 0
	combinedContent := ""
	for _, msg := range req.Messages {
		totalLength += len(msg.Content)
		combinedContent += msg.Content + "\n"
	}

	// If prompt is massive, gemini might be better for deep logic
	if totalLength > 4000 {
		return true
	}

	// Complexity Threshold 2: Math/Logic keywords
	complexPatterns := []string{
		`(?i)\b(?:calculate|equation|integral|derivative|algorithm|theorem|prove|logic puzzle)\b`,
		`\b[0-9]+(?:\.[0-9]+)?\s*[\*\/\+]\s*[0-9]+`,
	}
	for _, pattern := range complexPatterns {
		matched, _ := regexp.MatchString(pattern, combinedContent)
		if matched {
			return true
		}
	}
	return false
}

// -----------------------------------------------------------------------------
// Provider Clients
// -----------------------------------------------------------------------------
func callDeepSeek(req *ChatRequest) (*OpenAIResponse, error) {
	reqBytes, err := json.Marshal(req)
	if err != nil {
		return nil, err
	}

	httpReq, err := http.NewRequest("POST", "https://api.deepseek.com/chat/completions", bytes.NewBuffer(reqBytes))
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+DeepSeekAPIKey)

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(httpReq)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("DeepSeek Error (%d): %s", resp.StatusCode, string(body))
	}

	var dsResp OpenAIResponse
	if err := json.NewDecoder(resp.Body).Decode(&dsResp); err != nil {
		return nil, err
	}
	return &dsResp, nil
}

func callGemini(req *ChatRequest) (*OpenAIResponse, error) {
	// Convert OpenAI request to Gemini request
	var contents []map[string]interface{}
	for _, msg := range req.Messages {
		role := "user"
		if msg.Role == "assistant" {
			role = "model"
		} else if msg.Role == "system" {
			continue // System handled differently in Gemini, for MVP treating as user or dropping
		}
		contents = append(contents, map[string]interface{}{
			"role": role,
			"parts": []map[string]string{
				{"text": msg.Content},
			},
		})
	}

	geminiReqBody := map[string]interface{}{
		"contents": contents,
	}

	reqBytes, _ := json.Marshal(geminiReqBody)
	url := fmt.Sprintf("https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key=%s", GeminiAPIKey)

	httpReq, err := http.NewRequest("POST", url, bytes.NewBuffer(reqBytes))
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Content-Type", "application/json")

	client := &http.Client{Timeout: 60 * time.Second}
	resp, err := client.Do(httpReq)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("Gemini Error (%d): %s", resp.StatusCode, string(body))
	}

	// Parse Gemini Response and map back to OpenAI Format
	var geminiResp struct {
		Candidates []struct {
			Content struct {
				Parts []struct {
					Text string `json:"text"`
				} `json:"parts"`
			} `json:"content"`
		} `json:"candidates"`
		UsageMetadata struct {
			PromptTokenCount     int `json:"promptTokenCount"`
			CandidatesTokenCount int `json:"candidatesTokenCount"`
			TotalTokenCount      int `json:"totalTokenCount"`
		} `json:"usageMetadata"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&geminiResp); err != nil {
		return nil, err
	}

	textResponse := ""
	if len(geminiResp.Candidates) > 0 && len(geminiResp.Candidates[0].Content.Parts) > 0 {
		textResponse = geminiResp.Candidates[0].Content.Parts[0].Text
	}

	finalResp := &OpenAIResponse{
		Id:      "chatcmpl-gemini-cascade",
		Object:  "chat.completion",
		Created: time.Now().Unix(),
		Model:   "gemini-1.5-pro",
		Choices: []struct {
			Message ChatMessage `json:"message"`
		}{
			{
				Message: ChatMessage{
					Role:    "assistant",
					Content: textResponse,
				},
			},
		},
	}
	finalResp.Usage.PromptTokens = geminiResp.UsageMetadata.PromptTokenCount
	finalResp.Usage.CompletionTokens = geminiResp.UsageMetadata.CandidatesTokenCount
	finalResp.Usage.TotalTokens = geminiResp.UsageMetadata.TotalTokenCount

	return finalResp, nil
}

// -----------------------------------------------------------------------------
// Handler
// -----------------------------------------------------------------------------
func handleCompletions(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	bodyBytes, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "Error reading body", http.StatusBadRequest)
		return
	}

	var chatReq ChatRequest
	if err := json.Unmarshal(bodyBytes, &chatReq); err != nil {
		http.Error(w, "Invalid JSON payload", http.StatusBadRequest)
		return
	}

	// Pre-Flight Logging Profile
	start := time.Now()
	providerUsed := "deepseek"

	// Routing logic
	var respData *OpenAIResponse
	if shouldRouteToGemini(&chatReq) {
		providerUsed = "gemini"
		respData, err = callGemini(&chatReq)
	} else {
		respData, err = callDeepSeek(&chatReq)
		// Fallback Cascade Escaltion
		if err != nil || (respData != nil && len(respData.Choices) > 0 && len(respData.Choices[0].Message.Content) < 5) {
			log.Printf("DeepSeek failed or returned uncertain response. Escalating to Gemini. Err: %v", err)
			providerUsed = "gemini"
			respData, err = callGemini(&chatReq)
		}
	}

	if err != nil {
		log.Printf("Proxy Error: %v", err)
		http.Error(w, "Internal AI Gateway Error", http.StatusBadGateway)
		return
	}

	// Async Logging (Redis would go here)
	go func(provider string, usage struct {
		PromptTokens     int `json:"prompt_tokens"`
		CompletionTokens int `json:"completion_tokens"`
		TotalTokens      int `json:"total_tokens"`
	}, duration time.Duration) {
		log.Printf("[TELEMETRY] Provider: %s | Tokens [P:%d C:%d T:%d] | Latency: %s",
			provider, usage.PromptTokens, usage.CompletionTokens, usage.TotalTokens, duration)
		// TODO: push to Redis
	}(providerUsed, respData.Usage, time.Since(start))

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(respData)
}

func main() {
	http.HandleFunc("/v1/chat/completions", handleCompletions)
	port := "8080"
	log.Printf("Starting MVP Proxy Router on :%s ...", port)
	if err := http.ListenAndServe(":"+port, nil); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}
