from .errors import ClassifiedProviderError as ClassifiedProviderError
from .errors import classify_provider_error as classify_provider_error
from .errors import extract_error_status as extract_error_status
from .presets import KEY_PREFIX_HINTS as KEY_PREFIX_HINTS
from .presets import PRESET_ORDER as PRESET_ORDER
from .presets import PRESETS as PRESETS
from .presets import SETUP_PRESETS as SETUP_PRESETS
from .presets import guess_preset_for_key as guess_preset_for_key
from .presets import is_preset_key as is_preset_key
from .presets_data import KEY_PREFIX_HINTS as KEY_PREFIX_HINTS_DATA
from .presets_data import PRESET_ORDER as PRESET_ORDER_DATA
from .presets_data import PRESETS as PRESET_DATA
from .service import DEFAULT_BASE_URLS as DEFAULT_BASE_URLS
from .service import DEFAULT_REQUIRES as DEFAULT_REQUIRES
from .service import DETECT_CONNECT_TIMEOUT as DETECT_CONNECT_TIMEOUT
from .service import DETECT_ENGINE_NAMES as DETECT_ENGINE_NAMES
from .service import DETECT_READ_TIMEOUT as DETECT_READ_TIMEOUT
from .service import DETECT_TARGETS as DETECT_TARGETS
from .service import PROVIDER_TYPES as PROVIDER_TYPES
from .service import LocalEngineHit as LocalEngineHit
from .service import ProviderError as ProviderError
from .service import ProvidersService as ProvidersService
from .service import RemoteModel as RemoteModel
from .service import assign_course_default_task as assign_course_default_task
from .service import assign_course_task as assign_course_task
from .service import assign_default_task as assign_default_task
from .service import assign_task as assign_task
from .service import detect_local_engines as detect_local_engines
from .service import fetch_remote_models as fetch_remote_models
from .service import infer_caps as infer_caps
from .service import list_assignments as list_assignments
from .service import list_course_assignments as list_course_assignments
from .service import list_course_default_assignments as list_course_default_assignments
from .service import list_default_assignments as list_default_assignments
from .service import seed_default_task_assignments as seed_default_task_assignments
from .setup import CrossProviderModelError as CrossProviderModelError
from .setup import SetupError as SetupError
from .setup import SetupOptions as SetupOptions
from .setup import SetupOutcome as SetupOutcome
from .setup import UnknownPresetError as UnknownPresetError
from .setup import set_default_model as set_default_model
from .setup import setup_provider_from_preset as setup_provider_from_preset

__all__ = [
    "DEFAULT_BASE_URLS",
    "DEFAULT_REQUIRES",
    "DETECT_CONNECT_TIMEOUT",
    "DETECT_ENGINE_NAMES",
    "DETECT_READ_TIMEOUT",
    "DETECT_TARGETS",
    "KEY_PREFIX_HINTS",
    "KEY_PREFIX_HINTS_DATA",
    "PRESETS",
    "PRESET_DATA",
    "PRESET_ORDER",
    "PRESET_ORDER_DATA",
    "PROVIDER_TYPES",
    "SETUP_PRESETS",
    "ClassifiedProviderError",
    "CrossProviderModelError",
    "ProviderError",
    "ProvidersService",
    "RemoteModel",
    "SetupError",
    "SetupOptions",
    "SetupOutcome",
    "UnknownPresetError",
    "assign_course_default_task",
    "assign_course_task",
    "assign_default_task",
    "assign_task",
    "classify_provider_error",
    "detect_local_engines",
    "extract_error_status",
    "fetch_remote_models",
    "guess_preset_for_key",
    "infer_caps",
    "is_preset_key",
    "list_assignments",
    "list_course_assignments",
    "list_course_default_assignments",
    "list_default_assignments",
    "seed_default_task_assignments",
    "set_default_model",
    "setup_provider_from_preset",
]
