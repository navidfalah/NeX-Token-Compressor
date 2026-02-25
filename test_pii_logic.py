import re
import os

word_dict = set()
dict_path = '/usr/share/dict/words'
if os.path.exists(dict_path):
    with open(dict_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            word = line.strip().lower()
            if word:
                word_dict.add(word)
                
print(f"Loaded {len(word_dict)} words from system dictionary")

def validate_name(val):
    if not word_dict:
        return True # Fallback if no dict
    parts = val.split()
    # A true "Name" often has the last name NOT in the dictionary, but this is tricky.
    # Instead, let's reject if BOTH words are standard dictionary words
    # e.g. "Software Engineer" -> software is in dict, engineer is in dict -> Reject
    # "Navid Falah" -> navid not in dict, falah not in dict -> Keep
    # "Sustainability Dimensions" -> both in dict -> Reject
    
    in_dict = sum(1 for p in parts if p.lower() in word_dict)
    if in_dict == len(parts):
        return False # Both are standard words, probably not a name
    return True

test_cases = [
    "Sustainability Dimensions",
    "Advanced Text",
    "Unsupervised Learning",
    "Software Engineer",
    "Integration Web",
    "Circular Cities",
    "Siegen Entwicklung",
    "Allgemeine Hochschulreife",
    "Technische Leitung",
    "Backend Developer",
    "Navid Falah",
    "John Doe",
    "Alan Turing"
]

for t in test_cases:
    print(f"{t}: {validate_name(t)}")

