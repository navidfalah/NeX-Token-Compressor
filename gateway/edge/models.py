"""
Firma-KI Gateway — Edge Node Models
Configuration for edge pre-processing servers and routing rules.
"""
import uuid
from django.db import models


class EdgeNode(models.Model):
    """
    Edge pre-processing server deployed in a local data center.
    Heavy client prompts are compressed at the edge before crossing the network.
    """
    REGION_EU_WEST = 'eu-west'
    REGION_EU_CENTRAL = 'eu-central'
    REGION_US_EAST = 'us-east'
    REGION_US_WEST = 'us-west'
    REGION_ASIA_PACIFIC = 'asia-pacific'
    REGION_CHOICES = [
        (REGION_EU_WEST, 'EU West (Ireland, Netherlands)'),
        (REGION_EU_CENTRAL, 'EU Central (Frankfurt, Siegen)'),
        (REGION_US_EAST, 'US East'),
        (REGION_US_WEST, 'US West'),
        (REGION_ASIA_PACIFIC, 'Asia Pacific'),
    ]

    SOVEREIGNTY_EU = 'eu'
    SOVEREIGNTY_US = 'us'
    SOVEREIGNTY_GLOBAL = 'global'
    SOVEREIGNTY_CHOICES = [
        (SOVEREIGNTY_EU, 'EU (GDPR Compliant)'),
        (SOVEREIGNTY_US, 'US'),
        (SOVEREIGNTY_GLOBAL, 'Global (No Restrictions)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, help_text='Node identifier (e.g., "Frankfurt Edge 1")')
    location = models.CharField(max_length=200, help_text='Physical location description')
    region = models.CharField(max_length=20, choices=REGION_CHOICES, default=REGION_EU_CENTRAL)
    data_sovereignty_zone = models.CharField(
        max_length=20, choices=SOVEREIGNTY_CHOICES, default=SOVEREIGNTY_EU,
        help_text='Data sovereignty zone — EU nodes ensure GDPR compliance'
    )
    
    endpoint_url = models.URLField(
        max_length=500, help_text='Edge node API endpoint for pre-processing'
    )
    health_check_url = models.URLField(
        max_length=500, blank=True, help_text='URL for health checks'
    )
    
    # Capabilities
    supports_compression = models.BooleanField(default=True)
    supports_pii_masking = models.BooleanField(default=True)
    supports_embedding = models.BooleanField(default=False)
    max_payload_mb = models.IntegerField(default=10, help_text='Max payload size in MB')
    
    # Status
    is_active = models.BooleanField(default=True)
    current_load_pct = models.FloatField(
        default=0.0, help_text='Current load percentage (0-100)'
    )
    avg_latency_ms = models.IntegerField(
        default=0, help_text='Average processing latency in ms'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['region', 'name']
        verbose_name = 'Edge Node'
        verbose_name_plural = 'Edge Nodes'

    def __str__(self):
        return f"{self.name} ({self.get_region_display()})"


class EdgeRoutingRule(models.Model):
    """
    Rules for routing requests to edge nodes based on source region
    and data sovereignty requirements.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE,
        related_name='edge_routing_rules',
        null=True, blank=True, help_text='Org-specific rule (null = global)'
    )
    
    source_region = models.CharField(
        max_length=20, choices=EdgeNode.REGION_CHOICES,
        help_text='Client source region to match'
    )
    target_node = models.ForeignKey(
        EdgeNode, on_delete=models.CASCADE, related_name='routing_rules'
    )
    
    # GDPR enforcement
    require_eu_sovereignty = models.BooleanField(
        default=True,
        help_text='Enforce that data stays within EU sovereignty zone'
    )
    
    priority = models.IntegerField(
        default=0, help_text='Higher priority rules are evaluated first'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-priority', 'source_region']
        verbose_name = 'Edge Routing Rule'
        verbose_name_plural = 'Edge Routing Rules'

    def __str__(self):
        return f"{self.source_region} → {self.target_node.name}"
