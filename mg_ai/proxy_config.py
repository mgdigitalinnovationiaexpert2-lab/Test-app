from typing import Any

from mg_ai.config import Configuration


def render(config: Configuration, benchmark_ids: set[str] | None = None) -> dict[str, Any]:
    deployments = []
    for candidate in config.models:
        benchmark = candidate.id in (benchmark_ids or set())
        if benchmark and (candidate.cost_class != "FREE" or candidate.random_router
                          or candidate.api_base is not None or not (
                              candidate.provider == "groq"
                              and candidate.credential_env == "GROQ_API_KEY"
                              or candidate.provider == "openrouter"
                              and candidate.credential_env == "OPENROUTER_API_KEY"
                              and candidate.model.endswith(":free"))):
            raise ValueError("benchmark deployment must be a pinned reviewed free candidate")
        if not candidate.enabled and not benchmark:
            continue
        prefixes = {"openrouter": "openrouter/", "groq": "groq/", "nvidia": "nvidia_nim/",
                    "openai-compatible": "openai/", "direct": ""}
        if candidate.provider not in prefixes:
            raise ValueError("unsupported execution adapter")
        params: dict[str, Any] = {"model": prefixes[candidate.provider] + candidate.model,
                                 "api_key": "os.environ/" + candidate.credential_env,
                                 "num_retries": 0, "timeout": 55}
        if candidate.api_base:
            params["api_base"] = candidate.api_base
        if candidate.provider == "openrouter":
            params["extra_body"] = {"provider": {"allow_fallbacks": False,
                                                  "require_parameters": True,
                                                  "max_price": {"prompt": 0, "completion": 0}}}
        deployments.append({"model_name": candidate.id, "litellm_params": params})
    return {"model_list": deployments,
            "general_settings": {"master_key": "os.environ/LITELLM_MASTER_KEY",
                                 "store_prompts_in_spend_logs": False,
                                 "disable_spend_logs": True,
                                 "forward_client_headers_to_llm_api": False},
            "litellm_settings": {"num_retries": 0, "request_timeout": 55,
                                 "turn_off_message_logging": True, "set_verbose": False,
                                 "cache": False, "drop_params": False,
                                 "success_callback": [], "failure_callback": []},
            "router_settings": {"num_retries": 0, "fallbacks": [],
                                "context_window_fallbacks": [], "content_policy_fallbacks": []}}
