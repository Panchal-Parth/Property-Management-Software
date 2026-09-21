from datetime import date
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Model(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class Login(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class NotificationDismissIn(Model):
    ids: list[str] = Field(min_length=1, max_length=500)

    @field_validator('ids')
    @classmethod
    def valid_ids(cls, values):
        if any(not re.fullmatch(r'(?:unit-\d+-after-\d+|lease-\d+-\d{4}-\d{2}-\d{2})', value) for value in values):
            raise ValueError('Invalid notification identifier')
        return list(dict.fromkeys(values))


class EmailRequest(Model):
    email: str = Field(min_length=3, max_length=254)

    @field_validator('email')
    @classmethod
    def valid_email(cls, value):
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('Enter a valid email address')
        return value.lower()


class SignupRequest(EmailRequest):
    name: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=12, max_length=256)


class CodeConfirm(EmailRequest):
    code: str = Field(pattern=r'^\d{6}$')


class PasswordReset(CodeConfirm):
    password: str = Field(min_length=12, max_length=256)


class PasswordChange(Model):
    password: str = Field(min_length=12, max_length=256)
    code: str = Field(pattern=r'^\d{6}$')


class EmailChange(Model):
    email: str = Field(min_length=3, max_length=254)
    current_code: str = Field(pattern=r'^\d{6}$')
    new_code: str = Field(pattern=r'^\d{6}$')

    @field_validator('email')
    @classmethod
    def valid_email(cls, value):
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('Enter a valid email address')
        return value.lower()


class PropertyIn(Model):
    name: str = Field(min_length=1, max_length=150)
    address: str = Field(min_length=1, max_length=500)
    kind: Literal["Apartment", "Commercial", "Mixed"]
    notes: str = Field(default="", max_length=4000)


class UnitIn(Model):
    tenant_id: int | None = Field(default=None, gt=0)
    expected_rent_cents: int | None = Field(default=None, ge=0, le=100_000_000_00, strict=True)
    kind: Literal["Residential", "Commercial"] = "Residential"
    notes: str = Field(default="", max_length=4000)
    property_id: int = Field(gt=0)
    label: str = Field(min_length=1, max_length=100)
    floor: str = Field(default="", max_length=60)
    unavailable: bool = False


class TenantIn(Model):
    name: str = Field(min_length=1, max_length=150)
    phone: str = Field(default="", max_length=60)
    email: str = Field(default="", max_length=254)
    emergency_contact: str = Field(default="", max_length=500)
    notes: str = Field(default="", max_length=4000)

    @field_validator('email')
    @classmethod
    def valid_email(cls, value):
        if value and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('Enter a valid email address or leave it blank')
        return value


class LeaseIn(Model):
    unit_id: int = Field(gt=0)
    tenant_ids: list[int] = Field(min_length=1, max_length=20)
    start_date: date
    end_date: date
    rent_cents: int = Field(ge=0, le=100_000_000_00, strict=True)
    deposit_cents: int = Field(default=0, ge=0, le=100_000_000_00, strict=True)
    cancelled: bool = False
    notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def valid_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("Lease end must be on or after its start")
        if len(set(self.tenant_ids)) != len(self.tenant_ids):
            raise ValueError("Choose each tenant once")
        return self


class MonthlyIn(Model):
    expected_rent_cents: int | None = Field(default=None, ge=0, le=100_000_000_00, strict=True)
    property_id: int = Field(gt=0)
    unit_id: int | None = Field(default=None, gt=0)
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    amounts: list[int] = Field(min_length=6, max_length=6)
    notes: str = Field(default="", max_length=4000)

    @field_validator('month')
    @classmethod
    def valid_month(cls, value):
        date.fromisoformat(value + '-01')
        return value

    @field_validator("amounts", mode="before")
    @classmethod
    def money(cls, value):
        if not isinstance(value, list) or any(type(n) is not int or n < 0 or n > 100_000_000_00 for n in value):
            raise ValueError("Amounts must be nonnegative integer cents")
        return value


class SettingsIn(Model):
    name: str = Field(min_length=1, max_length=150)
    currency: Literal["USD", "CAD", "GBP", "EUR", "INR"]
    timezone: str = Field(min_length=1, max_length=80)
    category5: str = Field(min_length=1, max_length=60)
    category6: str = Field(min_length=1, max_length=60)

    @field_validator("timezone")
    @classmethod
    def zone(cls, value):
        from zoneinfo import ZoneInfo
        try:
            ZoneInfo(value)
        except Exception:
            raise ValueError("Use an IANA timezone such as America/New_York")
        return value


class DocumentIn(Model):
    filename: str = Field(min_length=1, max_length=180)
    kind: Literal["Lease", "Tenant", "Receipt", "Property", "Other"] = "Other"
    notes: str = Field(default="", max_length=4000)
    property_id: int | None = Field(default=None, gt=0)
    unit_id: int | None = Field(default=None, gt=0)
    tenant_id: int | None = Field(default=None, gt=0)
    lease_id: int | None = Field(default=None, gt=0)
    record_id: int | None = Field(default=None, gt=0)


class DepositIn(Model):
    lease_id: int = Field(gt=0)
    kind: Literal["received", "refunded", "deducted"]
    amount_cents: int = Field(gt=0, le=100_000_000_00, strict=True)
    date: date
    notes: str = Field(default="", max_length=4000)
