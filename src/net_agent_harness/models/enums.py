from enum import Enum


class TargetScope(str, Enum):
    device = "device"
    site = "site"
    ambiguous = "ambiguous"

class RunStage(str, Enum):
    INTAKE = "intake"
    DISCOVER = "discover"
    PLAN = "plan"
    RENDER = "render"
    VALIDATE = "validate"
    APPROVAL_PENDING = "approval_pending"
    EXECUTE = "execute"
    VERIFY = "verify"
    COMPLETE = "complete"
    FAILED = "failed"


class ChangeRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class NetworkDomain(str, Enum):
    VLAN = "vlan"
    ACL = "acl"
    PREFIX_LIST = "prefix-list"
    ROUTE_MAP = "route-map"
    ROUTING = "routing"
    WIRELESS = "wireless"
    OTHER = "other"


class ResourceType(str, Enum):
    SITE = "site"
    DEVICE = "device"
    INTERFACE = "interface"
    VLAN = "vlan"
    VRF = "vrf"
    SUBNET = "subnet"
    PREFIX = "prefix"
    IP_ASSIGNMENT = "ip_assignment"
    TOPOLOGY_LINK = "topology_link"


class RequestKind(str, Enum):
    ASK = "ask"
    PLAN = "plan"
    REVIEW = "review"


class Capability(str, Enum):
    TOPOLOGY = "topology"
    IPAM = "ipam"
    CHANGE = "change"
    INCIDENT = "incident"


class RoutingStatus(str, Enum):
    ROUTED = "routed"
    NEEDS_CLARIFICATION = "needs_clarification"
    BLOCKED = "blocked"

class ValidationStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class DeviceVendor(str, Enum):
    CISCO = "cisco"
    JUNIPER = "juniper"
    ARISTA = "arista"
    PALO_ALTO = "palo_alto"
    FORTINET = "fortinet"
    MERAKI = "meraki"
    OTHER = "other"

class SwitchportMode(str, Enum):
    ACCESS = "access"
    TRUNK = "trunk"

class AllowedVlansMode(str, Enum):
    ALL = "all"
    LIST = "list"
    NONE = "none"

class InterfaceType(str, Enum):
    SWITCHPORT = "switchport"
    ROUTED = "routed"

class SpanningTreeMode(str, Enum):
    EDGE = "edge"
    TRUNK = "trunk"
    EDGE_TRUNK = "edge trunk"
    NONE = "none"

class PlanDecisionType(str, Enum):
    APPLY = "apply"
    NO_OP = "no_op"
    BLOCKED = "blocked"

class RenderBackendType(str, Enum):
    API = "api"
    TERRAFORM = "terraform"
    ANSIBLE = "ansible"
    CLI = "cli"

class RenderRole(str, Enum):
    PRIMARY = "primary"
    FALLBACK = "fallback"


class WorkflowFamily(str, Enum):
    DISCOVERY = "discovery"
    CHANGE = "change"
    INCIDENT = "incident"


class IntentStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    
class ResourceLifecycleState(str, Enum):
    """Lifecycle state for a managed network resource or planned change.

    States follow the change pipeline from intent through verification:

    - ``current``  – reflects what is actually deployed right now.
    - ``intended`` – the desired end-state expressed as policy-level intent;
                     not yet modelled as a concrete diff.
    - ``planned``  – change has been modelled and diffed; not yet approved.
                     IPAM allocations that are reserved for a planned change
                     also sit here.
    - ``approved`` – change has passed an approval gate; not yet applied.
    - ``applied``  – change has been pushed to the device; not yet verified.
    - ``verified`` – applied change has been confirmed to match intent.
    """

    CURRENT = "current"
    INTENDED = "intended"
    PLANNED = "planned"
    APPROVED = "approved"
    APPLIED = "applied"
    VERIFIED = "verified"
