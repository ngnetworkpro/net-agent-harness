from enum import Enum


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
    OTHER = "other"
