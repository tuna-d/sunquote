from pydantic import Field

from sunquote.config import Settings


class EvalSettings(Settings):
    eval_delay_seconds: float = Field(default=15.0, ge=0, allow_inf_nan=False)
