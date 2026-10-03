"""Turning HTML form data into validated schemas and readable Russian error messages."""

from collections.abc import Mapping

from pydantic import ValidationError

# Pydantic error type -> Russian message ({…} placeholders are filled from the error context).
ERROR_MESSAGES = {
    "missing": "Обязательное поле",
    "greater_than": "Значение должно быть больше нуля",
    "decimal_parsing": "Введите число, например 12,50",
    "decimal_max_places": "Не больше {decimal_places} знаков после запятой",
    "decimal_max_digits": "Слишком большое число",
    "decimal_whole_digits": "Слишком большое число",
    "date_parsing": "Введите дату",
    "date_from_datetime_parsing": "Введите дату",
    "enum": "Выберите значение из списка",
    "int_parsing": "Некорректное значение",
    "string_too_long": "Не длиннее {max_length} символов",
}
DECIMAL_FIELDS = {"amount", "manual_rate"}


def clean_form(data: Mapping[str, str]) -> dict[str, str]:
    """Drop empty fields (so defaults apply) and accept a comma as the decimal separator."""
    cleaned = {}
    for key, value in data.items():
        value = value.strip()
        if not value:
            continue
        cleaned[key] = value.replace(" ", "").replace(",", ".") if key in DECIMAL_FIELDS else value
    return cleaned


def form_errors(exc: ValidationError) -> dict[str, str]:
    """{"amount": "Значение должно быть больше нуля", ...}; model-level errors go to "__all__"."""
    errors: dict[str, str] = {}
    for error in exc.errors():
        field = str(error["loc"][0]) if error["loc"] else "__all__"
        if error["type"] == "value_error":
            message = str(error["ctx"]["error"])  # our own messages are already in Russian
        else:
            template = ERROR_MESSAGES.get(error["type"], "Некорректное значение")
            message = template.format(**error.get("ctx", {}))
        errors.setdefault(field, message)
    return errors
