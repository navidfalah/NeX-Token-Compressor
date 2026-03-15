"""
Firma-KI Gateway — Edge Router
Selects optimal edge node for pre-processing based on client region,
load balancing, and data sovereignty requirements.
"""
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
from models.gateway import EdgeNode, EdgeRoutingRule


class EdgeRouter:
    """
    Edge-Native Processing Router.
    """

    EU_IP_RANGES = {
        'eu-central': [
            r'^(?:5\.(?:2[56789]|[34]\d))',
            r'^(?:46\.(?:2[0-9]{2}))',
            r'^(?:193\.(?:1\d{2}))',
        ],
        'eu-west': [
            r'^(?:51\.)',
            r'^(?:52\.)',
        ],
    }

    @classmethod
    async def select_edge_node_async(cls, db: AsyncSession, client_ip: str = '',
                                    organization=None,
                                    require_eu_sovereignty: bool = True):
        """
        Select the best edge node for this request.
        """
        # Detect client region
        client_region = cls._detect_region(client_ip)

        # Find matching routing rules
        stmt = select(EdgeRoutingRule).where(
            EdgeRoutingRule.is_active == True,
            EdgeRoutingRule.source_region == client_region
        ).order_by(desc(EdgeRoutingRule.priority))

        result = await db.execute(stmt)
        rules = result.scalars().all()

        # Filter by organization and sovereignty
        best_node = None
        best_load = float('inf')

        # Heuristic: try org-specific rules first, then global rules
        org_id = organization.id if organization else None
        
        filtered_rules = [r for r in rules if r.organization_id == org_id]
        if not filtered_rules and org_id:
            filtered_rules = [r for r in rules if r.organization_id is None]
        
        for rule in filtered_rules:
            # We need to fetch the node. In async, we should probably join or fetch.
            stmt_node = select(EdgeNode).where(EdgeNode.id == rule.target_node_id)
            res_node = await db.execute(stmt_node)
            node = res_node.scalar_one_or_none()
            
            if node and node.is_active:
                if require_eu_sovereignty and node.data_sovereignty_zone != 'eu':
                    continue
                if node.current_load_pct < best_load:
                    best_node = node
                    best_load = node.current_load_pct

        # Fallback: find any active EU node
        if not best_node and require_eu_sovereignty:
            stmt_fallback = select(EdgeNode).where(
                EdgeNode.is_active == True,
                EdgeNode.data_sovereignty_zone == 'eu'
            ).order_by(EdgeNode.current_load_pct).limit(1)
            res_fallback = await db.execute(stmt_fallback)
            best_node = res_fallback.scalar_one_or_none()

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
    def _detect_region(cls, ip: str) -> str:
        for region, patterns in cls.EU_IP_RANGES.items():
            for pattern in patterns:
                if re.match(pattern, ip):
                    return region
        return 'eu-central'

    @classmethod
    def get_compliance_report(cls, edge_node) -> dict:
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
            'encryption_in_transit': True,
            'data_residency': (
                'Data processed and stored within EU jurisdiction'
                if is_eu else
                f'Data may be processed outside EU ({edge_node.data_sovereignty_zone})'
            ),
        }
