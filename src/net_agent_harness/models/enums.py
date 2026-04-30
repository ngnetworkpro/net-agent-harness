from enum import Enum


class ChangeRisk(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"



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
