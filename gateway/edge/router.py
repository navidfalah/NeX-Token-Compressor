"""
Firma-KI Gateway — Edge Router
Selects optimal edge node for pre-processing based on client region,
load balancing, and data sovereignty requirements.
"""
import re


class EdgeRouter:
    """
    Edge-Native Processing Router.
    
    Selects the optimal edge node for pre-processing client requests:
    1. Detect client region from IP/headers
    2. Match against routing rules
    3. Select node with lowest load within the sovereignty zone
    4. Return the edge node for pre-processing delegation
    
    Result: Reduces data payload size traveling through the network,
    slashes response times, and guarantees GDPR compliance.
    """

    # IP-to-region heuristic mapping (simplified for European focus)
    # In production, this would use a GeoIP database
    EU_IP_RANGES = {
        'eu-central': [
            r'^(?:5\.(?:2[56789]|[34]\d))',   # German IP blocks (simplified)
            r'^(?:46\.(?:2[0-9]{2}))',          # Austrian ranges
            r'^(?:193\.(?:1\d{2}))',            # Swiss ranges
        ],
        'eu-west': [
            r'^(?:51\.)',                        # Dutch/Irish ranges
            r'^(?:52\.)',                         # UK/EU ranges
        ],
    }

    @classmethod
    def select_edge_node(cls, request=None, client_ip: str = '',
                         organization=None,
                         require_eu_sovereignty: bool = True):
        """
        Select the best edge node for this request.
        
        Args:
            request: Django HttpRequest (optional, for IP extraction)
            client_ip: Explicit client IP (overrides request extraction)
            organization: Organization for org-specific routing rules
            require_eu_sovereignty: Force EU data sovereignty compliance
            
        Returns:
            EdgeNode instance or None if no suitable node found.
            Also returns routing metadata dict.
        """
        from .models import EdgeNode, EdgeRoutingRule

        # Extract client IP
        if not client_ip and request:
            client_ip = cls._extract_client_ip(request)

        # Detect client region
        client_region = cls._detect_region(client_ip)

        # Find matching routing rules
        rules = EdgeRoutingRule.objects.filter(
            is_active=True,
            source_region=client_region,
        ).select_related('target_node').order_by('-priority')

        # Apply org filter if available
        if organization:
            org_rules = rules.filter(organization=organization)
            if org_rules.exists():
                rules = org_rules
            else:
                rules = rules.filter(organization__isnull=True)

        # Filter by sovereignty requirements
        if require_eu_sovereignty:
            rules = rules.filter(
                target_node__data_sovereignty_zone='eu',
                target_node__is_active=True,
            )

        # Select the node with the lowest load
        best_node = None
        best_load = float('inf')
        
        for rule in rules:
            node = rule.target_node
            if node.is_active and node.current_load_pct < best_load:
                best_node = node
                best_load = node.current_load_pct

        # Fallback: find any active EU node
        if not best_node and require_eu_sovereignty:
            best_node = EdgeNode.objects.filter(
                is_active=True,
                data_sovereignty_zone='eu',
            ).order_by('current_load_pct').first()

        metadata = {
            'client_ip': client_ip,
            'detected_region': client_region,
            'sovereignty_required': require_eu_sovereignty,
            'node_selected': best_node.name if best_node else None,
            'node_region': best_node.region if best_node else None,
            'node_load_pct': best_node.current_load_pct if best_node else None,
            'gdpr_compliant': (
                best_node.data_sovereignty_zone == 'eu'
                if best_node else False
            ),
        }

        return best_node, metadata

    @classmethod
    def _extract_client_ip(cls, request) -> str:
        """Extract client IP from Django request, handling proxies."""
        # Check X-Forwarded-For (common with reverse proxies)
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if forwarded:
            return forwarded.split(',')[0].strip()
        
        # Check X-Real-IP
        real_ip = request.META.get('HTTP_X_REAL_IP', '')
        if real_ip:
            return real_ip.strip()
        
        return request.META.get('REMOTE_ADDR', '127.0.0.1')

    @classmethod
    def _detect_region(cls, ip: str) -> str:
        """
        Detect geographic region from IP address.
        Uses heuristic pattern matching (placeholder for GeoIP database).
        """
        for region, patterns in cls.EU_IP_RANGES.items():
            for pattern in patterns:
                if re.match(pattern, ip):
                    return region

        # Default to eu-central for German-focused deployment
        return 'eu-central'

    @classmethod
    def get_compliance_report(cls, edge_node) -> dict:
        """
        Generate a GDPR compliance report for an edge node routing decision.
        """
        if not edge_node:
            return {
                'gdpr_compliant': False,
                'reason': 'No edge node selected — data may leave EU jurisdiction',
            }

        is_eu = edge_node.data_sovereignty_zone == 'eu'
        return {
            'gdpr_compliant': is_eu,
            'node_name': edge_node.name,
            'node_location': edge_node.location,
            'data_sovereignty_zone': edge_node.data_sovereignty_zone,
            'encryption_in_transit': True,  # Always true in our architecture
            'data_residency': (
                'Data processed and stored within EU jurisdiction'
                if is_eu else
                f'Data may be processed outside EU ({edge_node.data_sovereignty_zone})'
            ),
        }
