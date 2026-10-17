"""Schema building blocks shared by feature schemas."""

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    """Read-model base: build a response straight from an ORM instance."""

    model_config = ConfigDict(from_attributes=True)
