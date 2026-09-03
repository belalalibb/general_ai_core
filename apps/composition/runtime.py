"""P-B — local-first runtime composition (Operator directive, Option A).

ONE profile builder turns the environment into a fully composed platform:

- **No env vars ⇒ in-memory everything** — the exact hermetic posture the
  whole test suite proves (byte-identical bindings; ADR-0002 dev/test
  profile). ``python3 -m apps.main`` on a laptop just works.
- **DATABASE_URL set ⇒ durable profile** — the P-A stores swap in at this
  root (executions P-A.1, identity P-A.2, source-change P-A.3, plus the
  V1 durable outbox/idempotency for the async path). Call sites stay
  byte-identical: only bindings change (P2).
- **GROQ_API_KEY / GSK_API_KEY set ⇒ real providers** — the recorded
  31 §19 step-13/14 flow: the MANIFESTs ship ``status="disabled"``; this
  composition root is the "enabled via Admin/Config" actor and flips the
  DOMAIN status to ACTIVE only because the providers' contract tests
  passed (T-IMPL-036/037, committed evidence). Keys enter through
  ``InMemorySecretManager`` → opaque credential_ref → adapter-side
  resolution; no raw secret ever reaches core (20 §5). Absent keys ⇒ the
  hermetic scripted provider serves (labeled ``local-echo`` — never
  pretending to be a real model, 41 §49).

Recorded P-B decisions (this module is their home):

1. **Worker + relay are caller-driven here too.** ``RuntimeProfile``
   exposes ``worker``/``relay`` objects with their proven ``run_once`` /
   ``recover_once`` / ``relay_once`` bodies; ``apps/main.py`` owns the
   asyncio cadence loops (core loop bodies stay cadence-free — the
   recorded core/runtime posture).
2. **create_app grew two optional store kwargs** (``source_proposals`` /
   ``source_snapshots``) so P-A.3 durability can bind WITHOUT this root
   reaching into workflow internals. Defaults unchanged (in-memory);
   ``authoritative_applier`` is NOT a parameter and stays None — §14.
3. **Durable identity needs a plan row** (``tenants.plan_id`` FK
   RESTRICT). ``ensure_default_plan`` seeds ONE idempotent
   ``local-default`` row at startup — composition DATA, exactly like the
   budget numbers (41 §19 posture), never a schema change.
4. **Email verification stays local**: MVP Phase 2 forbids real delivery,
   so the binding LOGS a delivery notice to stdout with the token —
   honest local-dev affordance (the operator reads the token from the
   console), never a fake SMTP claim (41 §49). The token is the
   verification secret by design here: single-process local profile.
5. **The default tenant budget is composition data**: the in-memory
   profile seeds one demo principal + budget so the API is usable
   immediately; the durable profile grants each REGISTERED tenant a
   budget at first use via the same ``configure_tenant`` admin seam.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO
from uuid import UUID, uuid4, uuid5

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from apps.admin_agent.tools import AgentToolSurface
from apps.api.admin import AdminSurface
from apps.api.app import Principal, create_app
from apps.api.auth import AuthSurface
from apps.api.engineering_admin import EngineeringAdminSurface
from apps.api.skills_import import SkillReviewSurface
from apps.api.store import ExecutionStorePort, InMemoryExecutionStore
from apps.api.worker import ExecutionMessageHandler
from apps.composition.admin_console import attach_admin_console
from apps.composition.agent import ComposedAgent, build_agent, grant_agent_tenant
from apps.composition.bridge import AsyncBridge
from apps.composition.database import (
    DatabaseBindings,
    build_database_bindings,
    database_settings_from_env,
)
from apps.composition.durability import build_durable_execution_store
from apps.composition.engineering import (
    build_engineering,
    grant_engineering_reads,
    grant_engineering_writes,
)
from apps.composition.gateway import gateway_settings_from_env
from apps.composition.identity import build_durable_identity_service
from apps.composition.provider_onboarding import (
    CatalogPersistence,
    build_onboarding_surface,
    hydrate_gateway_providers,
    replay_admin_status_overrides,
)
from apps.composition.sourcechange import build_durable_sourcechange_stores
from apps.composition.workspaces import build_durable_workspace_stores
from core.admin.service import AdminConfigService
from core.agent import (
    DEFAULT_AGENT_DEADLINE_MS,
    DEFAULT_AGENT_MAX_STEPS,
    DEFAULT_REASONING_MAX_TOKENS,
    MAX_AGENT_MAX_STEPS,
    MAX_REASONING_MAX_TOKENS,
    MIN_REASONING_MAX_TOKENS,
)
from core.audit.memory import InMemoryAuditLog
from core.context.composer import ContextComposer
from core.contracts.domain import (
    AuthType,
    BindingAvailability,
    CredentialStatus,
    Modality,
    Model,
    ModelStatus,
    ModelTier,
    Provider,
    ProviderModelBinding,
    ProviderStatus,
)
from core.contracts.identity import Tenant, User
from core.contracts.provider import (
    CredentialHealth,
    DiscoveredModel,
    HealthScope,
    ProviderCapabilities,
    ProviderError,
    ProviderErrorCategory,
    ProviderGenerateRequest,
    ProviderGenerateResponse,
    ProviderHealth,
    ProviderHealthState,
    ProviderManifest,
)
from core.evaluation.memory import InMemoryEvaluationStore
from core.execution.service import ExecutionService
from core.identity.ports import IdentityServicePort
from core.identity.service import InMemoryIdentityService, Session
from core.memory.memory import InMemoryConversationStore, InMemoryMemoryStore
from core.providers.ports import ProviderAdapterPort
from core.providers.registry import BindingRegistry, ModelRegistry, ProviderRegistry
from core.roles.registry import RoleRegistry, SkillRegistry
from core.routing.router import SimpleScoringRouter
from core.runtime.memory import InMemoryQueue, InMemoryRateLimiter
from core.runtime.outbox import InMemoryOutbox, OutboxPort, OutboxRecord, OutboxRelay
from core.runtime.worker import IdempotencyPort, InMemoryIdempotencyStore, Worker
from core.secrets.memory import InMemorySecretManager
from core.skills.importing import SkillImportService
from core.tools.source_reader import SourceReader
from core.usage.memory import InMemoryUsageAccounting
from infrastructure.security.password import Argon2idPasswordHasher
from providers.real.genspark_llm import (
    MANIFEST as GENSPARK_MANIFEST,
)
from providers.real.genspark_llm import (
    VERIFIED_TEXT_MODELS as GENSPARK_MODELS,
)
from providers.real.genspark_llm import (
    GensparkLLMAdapter,
)
from providers.real.groq import (
    MANIFEST as GROQ_MANIFEST,
)
from providers.real.groq import (
    VERIFIED_TEXT_MODELS as GROQ_MODELS,
)
from providers.real.groq import (
    GroqAdapter,
)

__all__ = [
    "DEFAULT_PLAN_NAME",
    "EXECUTE_STREAM",
    "BridgedIdempotency",
    "BridgedOutbox",
    "BudgetGrantingIdentity",
    "ConsoleEmailSender",
    "RuntimeProfile",
    "build_runtime_profile",
    "ensure_default_plan",
]

EXECUTE_STREAM = "executions.requests"
WORKER_GROUP = "executions"
WORKER_CONSUMER = "local-worker-1"
DEFAULT_PLAN_NAME = "local-default"
#: Stable UUID for the seeded local plan row (uuid5 over a fixed namespace
#: string — deterministic across restarts so the seed is idempotent).
DEFAULT_PLAN_ID = uuid5(UUID("00000000-0000-0000-0000-000000000000"), DEFAULT_PLAN_NAME)
#: Composition DATA (41 §19 posture — no doc defines numeric defaults, the
#: root opts in): generous local budget; VPS operators change env instead.
DEFAULT_TASK_UNITS = 1_000_000.0
#: repo_root/ui/app — the P-D.2 end-user static shell (the PROVEN
#: ui/admin StaticFiles posture, apps/composition/admin_console.py).
UI_APP_DIR = Path(__file__).resolve().parents[2] / "ui" / "app"
_ENV_ADMIN_EMAILS = "ADMIN_EMAILS"
#: R165 operator caps for the shared agent runtime (per run). Bounded by the
#: runtime's hard cap (32 steps); invalid/absent ⇒ the core defaults.
_ENV_AGENT_MAX_STEPS = "AGENT_MAX_STEPS"
_ENV_AGENT_DEADLINE_MS = "AGENT_DEADLINE_MS"
_ENV_AGENT_REASONING_MAX_TOKENS = "AGENT_REASONING_MAX_TOKENS"
_ENV_GROQ_KEY = "GROQ_API_KEY"
_ENV_GSK_KEY = "GSK_API_KEY"


@dataclass
class BridgedOutbox:
    """OutboxPort that routes EVERY call across the AsyncBridge loop.

    Why (P-B recorded fact): asyncpg pools are loop-bound. The durable
    stores already run all their engine work on the bridge loop; the
    async-execute path and the relay would otherwise touch the SAME pool
    from the SERVER loop — "Future attached to a different loop". One
    loop owns the pool; every doorway crosses the bridge (P1).
    """

    inner: OutboxPort
    bridge: AsyncBridge

    async def append(self, stream: str, payload: Mapping[str, str], idempotency_key: str) -> str:
        return await self.bridge.run_async(self.inner.append(stream, payload, idempotency_key))

    async def pending(self, max_records: int = 1) -> tuple[OutboxRecord, ...]:
        return await self.bridge.run_async(self.inner.pending(max_records))

    async def mark_dispatched(self, record_id: str) -> None:
        await self.bridge.run_async(self.inner.mark_dispatched(record_id))


@dataclass
class BridgedIdempotency:
    """IdempotencyPort across the bridge — same loop-affinity fact."""

    inner: IdempotencyPort
    bridge: AsyncBridge

    async def seen(self, key: str) -> bool:
        return await self.bridge.run_async(self.inner.seen(key))

    async def record(self, key: str) -> None:
        await self.bridge.run_async(self.inner.record(key))


class ConsoleEmailSender:
    """EmailVerificationPort — honest local delivery (recorded decision 4).

    MVP Phase 2 forbids real email delivery; the local runtime prints the
    verification token to the process console so the operator can complete
    the flow. This is labeled behavior, not a fake SMTP claim (41 §49).
    The write targets ``stream`` (stdout by default; injectable for tests).
    """

    def __init__(self, stream: TextIO | None = None) -> None:
        # Resolved LAZILY at send time so stdout redirection (tests,
        # process managers) always reaches the current stream.
        self._stream = stream

    def send_verification(self, email: str, token: str) -> None:
        message = json.dumps(
            {
                "event": "email_verification_token_issued",
                "delivery": "console (MVP Phase 2: real email delivery forbidden)",
                "email": email,
                "token": token,
            }
        )
        stream = self._stream if self._stream is not None else sys.stdout
        print(message, file=stream, flush=True)  # noqa: T201 — recorded local affordance


@dataclass
class BudgetGrantingIdentity:
    """IdentityServicePort wrapper — recorded decision 5 made real.

    Usage accounting is still process-local (durable usage is a later,
    honestly-scoped binding), so a durable-profile tenant needs its
    budget granted in THIS process. The wrapper delegates every call to
    the inner service and grants the composition-data default budget the
    first time a tenant appears (register / login / session resolution —
    the last one covers sessions that survived a restart). Same
    ``configure_tenant`` admin seam as everywhere else; plan changes via
    admin still work (configure preserves consumed history).
    """

    inner: IdentityServicePort
    usage: InMemoryUsageAccounting
    #: R160: further first-appearance grants (the shared agent firewall's
    #: read-only tenant policy) ride the SAME seam — one derivation of
    #: "tenant appeared", two consumers.
    on_tenant: list[Callable[[UUID], None]] = field(default_factory=list)
    _granted: set[UUID] = field(default_factory=set)

    def _grant(self, tenant_id: UUID) -> None:
        if tenant_id not in self._granted:
            self.usage.configure_tenant(
                tenant_id,
                plan=DEFAULT_PLAN_NAME,
                task_units_limit=DEFAULT_TASK_UNITS,
            )
            for hook in self.on_tenant:
                hook(tenant_id)
            self._granted.add(tenant_id)

    def register(self, email: str, password: str, preferred_language: str) -> User:
        user = self.inner.register(email, password, preferred_language)
        self._grant(user.tenant_id)
        return user

    def verify_email(self, token: str) -> User:
        return self.inner.verify_email(token)

    def login(self, email: str, password: str) -> Session:
        session = self.inner.login(email, password)
        self._grant(session.tenant_id)
        return session

    def resolve_session(self, token: str) -> Session:
        session = self.inner.resolve_session(token)
        self._grant(session.tenant_id)
        return session

    def logout(self, token: str) -> None:
        self.inner.logout(token)

    def get_user_for_session(self, token: str) -> User:
        user = self.inner.get_user_for_session(token)
        self._grant(user.tenant_id)
        return user

    def get_tenant(self, tenant_id: UUID, *, session_token: str) -> Tenant:
        return self.inner.get_tenant(tenant_id, session_token=session_token)


class LocalEchoAdapter:
    """Hermetic ProviderAdapterPort for the no-keys local profile.

    Echoes the request payload back as the output, honestly labeled —
    the local runtime must be exercisable WITHOUT any real credential,
    and must never pretend a real model answered (41 §49).
    """

    def __init__(self, manifest: ProviderManifest) -> None:
        self._manifest = manifest

    def get_manifest(self) -> ProviderManifest:
        return self._manifest

    async def validate_credential(self, credential_ref: str) -> CredentialHealth:
        return CredentialHealth(credential_ref=credential_ref, status=CredentialStatus.ACTIVE)

    async def discover_models(self, account_id: UUID | None = None) -> list[DiscoveredModel]:
        return []

    async def get_capabilities(self) -> ProviderCapabilities:
        return self._manifest.capabilities

    async def generate(self, request: ProviderGenerateRequest) -> ProviderGenerateResponse:
        ask = request.payload.get("ask", "")
        output: dict[str, object] = {
            "provider": "local-echo",
            "note": "hermetic local adapter — no real model was called",
            "echo": ask,
        }
        # R161: echo the composed 13 §5 context the adapter RECEIVED — the
        # local profile then shows, honestly, that learned (GOLD) knowledge
        # reached the model input. The real gateway adapter sends the same
        # object as a system message; this is the hermetic mirror of that.
        context = request.payload.get("context")
        if isinstance(context, dict):
            blocks = context.get("context_blocks")
            if isinstance(blocks, list):
                output["context_blocks"] = [
                    {"type": b.get("type"), "content": b.get("content"), "source": b.get("source")}
                    for b in blocks
                    if isinstance(b, dict)
                ]
        return ProviderGenerateResponse(
            request_id=request.request_id,
            succeeded=True,
            output=output,
            usage={"units": 1},
            latency_ms=0,
        )

    async def health_check(self, scope: HealthScope) -> ProviderHealth:
        return ProviderHealth(provider_id=self._manifest.id, state=ProviderHealthState.HEALTHY)

    def normalize_error(self, error: object) -> ProviderError:
        return ProviderError(
            category=ProviderErrorCategory.NON_RETRYABLE_ERROR,
            retryable=False,
            safe_message="local echo failure",
        )


def _echo_manifest() -> ProviderManifest:
    return ProviderManifest.model_validate(
        {
            "id": "local_echo",
            "name": "Local Echo (hermetic)",
            "version": "1.0.0",
            "status": "active",
            "auth": {"types": ["api_key"], "supports_refresh": False},
            "account_pool": {"supported": False},
            "capabilities": {"chat": True},
            "operations": ["generate_text"],
            "models": {"discovery": "static", "static_models": ["local-echo-1"]},
            "rate_limits": {"strategy": "provider_defined"},
            "health": {"checks": ["ping"]},
            "errors": {"mapping": "inline"},
        }
    )


def _model(key: str, *, tier: ModelTier) -> Model:
    """Registry Model row for a provider-declared model name (never invented)."""
    return Model(
        id=uuid4(),
        model_key=key,
        display_name=key,
        tier=tier,
        modalities=[Modality.TEXT],
        capabilities=["reasoning"],
        quality_score=0.8,
        reliability_score=0.8,
        cost_score=0.8,
        speed_score=0.8,
        status=ModelStatus.ACTIVE,
    )


@dataclass
class RuntimeProfile:
    """Everything ``apps/main.py`` needs to serve and to shut down.

    ``bridge``/``bindings`` are None on the in-memory profile; the
    entrypoint's lifespan closes whichever exist (owner disposes —
    the recorded DatabaseBindings/AsyncBridge posture).
    """

    app: FastAPI
    worker: Worker
    relay: OutboxRelay
    outbox: OutboxPort
    identity: IdentityServicePort | None
    usage: InMemoryUsageAccounting
    providers: ProviderRegistry
    models: ModelRegistry
    bindings_registry: BindingRegistry
    durable: bool
    bridge: AsyncBridge | None = None
    bindings: DatabaseBindings | None = None
    demo_principal: Principal | None = None
    # Diagnostics for the startup banner (never secrets): provider keys bound.
    provider_keys: tuple[str, ...] = field(default_factory=tuple)
    # R160: the SHARED agent composition (surface + authority chain).
    agent: ComposedAgent | None = None
    # S2: the bound provider adapters (the SAME instances ExecutionService
    # calls). Retained so the lifespan can release pooled HTTP clients at
    # shutdown (owner disposes) — see ``release_adapters``.
    adapters: Mapping[UUID, ProviderAdapterPort] = field(default_factory=dict)

    async def release_adapters(self) -> int:
        """Close every adapter that owns a pooled client (S2 shutdown).

        ``aclose`` is NOT part of ``ProviderAdapterPort`` (adapters without
        long-lived resources need none); adapters that expose it are closed
        idempotently. Returns the number of adapters released.
        """
        released = 0
        for adapter in self.adapters.values():
            closer = getattr(adapter, "aclose", None)
            if callable(closer):
                await closer()
                released += 1
        return released


def ensure_default_plan(bindings: DatabaseBindings, bridge: AsyncBridge) -> UUID:
    """Idempotently seed the local default plan row (recorded decision 3).

    ``tenants.plan_id`` is a RESTRICT FK — registration cannot create a
    tenant without an existing plan. The row is composition DATA with a
    deterministic id; re-running is a no-op (ON CONFLICT DO NOTHING).
    """

    async def _seed() -> None:
        async with bindings.session_factory() as session:
            await session.execute(
                text(
                    "INSERT INTO plans (id, name) VALUES (:id, :name) ON CONFLICT (id) DO NOTHING"
                ),
                {"id": DEFAULT_PLAN_ID, "name": DEFAULT_PLAN_NAME},
            )
            await session.commit()

    bridge.run(_seed())
    return DEFAULT_PLAN_ID


def _bind_real_providers(
    environ: Mapping[str, str],
    providers: ProviderRegistry,
    models: ModelRegistry,
    bindings: BindingRegistry,
    adapters: MutableMapping[UUID, ProviderAdapterPort],
    credential_refs: MutableMapping[UUID, str],
) -> list[str]:
    """Bind Groq / Genspark LLM when their keys are present (20 §5 flow).

    Keys → InMemorySecretManager → opaque ref → adapter-side resolver.
    The domain ProviderStatus flips to ACTIVE here — the 31 §19 step-14
    "enabled via Admin/Config" act, justified by the committed contract-
    test evidence (T-IMPL-036/037). MANIFESTs stay disabled (they are
    the shipped declaration; the DOMAIN row is the composition's truth).
    """
    bound: list[str] = []
    secrets = InMemorySecretManager()
    platform_tenant = uuid4()  # the composition's own custody scope

    def _resolver(credential_ref: str) -> str:
        return secrets.resolve(platform_tenant, credential_ref)

    specs: list[
        tuple[
            str,
            str,
            ProviderManifest,
            tuple[str, ...],
            Callable[..., ProviderAdapterPort],
        ]
    ] = []
    groq_key = environ.get(_ENV_GROQ_KEY, "").strip()
    if groq_key:
        specs.append(("groq", groq_key, GROQ_MANIFEST, GROQ_MODELS, GroqAdapter))
    gsk_key = environ.get(_ENV_GSK_KEY, "").strip()
    if gsk_key:
        specs.append(
            (
                "genspark_llm",
                gsk_key,
                GENSPARK_MANIFEST,
                GENSPARK_MODELS,
                GensparkLLMAdapter,
            )
        )

    for provider_key, key, manifest, model_names, adapter_factory in specs:
        ref = secrets.store(platform_tenant, key)
        adapter = adapter_factory(manifest, secret_resolver=_resolver, health_credential_ref=ref)
        provider = Provider(
            id=uuid4(),
            provider_key=provider_key,
            display_name=manifest.name,
            # 31 §19 step 14: contract tests passed (committed evidence) ⇒
            # this root — the Admin/Config actor locally — enables it.
            status=ProviderStatus.ACTIVE,
            auth_types=[AuthType.API_KEY],
            supports_account_pool=False,
        )
        providers.register(provider, manifest)
        for name in model_names:
            model = _model(name, tier=ModelTier.MEDIUM)
            models.register(model)
            bindings.register(
                ProviderModelBinding(
                    provider_id=provider.id,
                    model_id=model.id,
                    provider_model_name=name,
                    availability=BindingAvailability.AVAILABLE,
                )
            )
        adapters[provider.id] = adapter
        credential_refs[provider.id] = ref
        bound.append(provider_key)
    return bound


def _agent_cap(raw: str | None, *, default: int, low: int, high: int) -> int:
    """R165: an operator cap from env, or ``default``. Out-of-range / non-int
    values fall back to the default (the platform never boots with a cap it
    cannot honour, and never silently exceeds the core hard cap)."""
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        return default
    return value if low <= value <= high else default


def _source_reader(root: str) -> SourceReader | None:
    """Mandate §9 seam: a jailed reader over AGENT_SOURCE_ROOT, or None.

    Deliberately forgiving at composition (absent/blank/invalid path means
    NO source tools — the platform never fails to boot over an optional
    inspection seam), while the reader itself stays strict at use.
    """
    candidate = root.strip()
    if not candidate:
        return None
    path = Path(candidate)
    if not path.is_dir():
        return None
    return SourceReader(root=path)


#: Bounded same-candidate retry budget for retryable provider errors
#: (rate_limited / retryable_server_error), Retry-After honored between
#: attempts. R165 live: Groq's free tier is 8k tokens/minute and a real
#: multi-step agent brief runs 2-4k tokens per proposal, so ONE retry after
#: a 9 s Retry-After met the cap again and the run died mid-task. The run's
#: deadline still bounds the total wait — no infinite retry (40 §4.6).
ENV_PROVIDER_RETRIES = "PROVIDER_MAX_RETRIES"
DEFAULT_PROVIDER_RETRIES = 1
MAX_PROVIDER_RETRIES = 8


def _provider_retries(env: Mapping[str, str]) -> int:
    raw = (env.get(ENV_PROVIDER_RETRIES) or "").strip()
    if not raw:
        return DEFAULT_PROVIDER_RETRIES
    try:
        value = int(raw)
    except ValueError as exc:
        msg = f"{ENV_PROVIDER_RETRIES} must be an integer 0-{MAX_PROVIDER_RETRIES}, got {raw!r}"
        raise ValueError(msg) from exc
    if not 0 <= value <= MAX_PROVIDER_RETRIES:
        msg = f"{ENV_PROVIDER_RETRIES} must be 0-{MAX_PROVIDER_RETRIES}, got {value}"
        raise ValueError(msg)
    return value


def _bind_echo_provider(
    providers: ProviderRegistry,
    models: ModelRegistry,
    bindings: BindingRegistry,
    adapters: MutableMapping[UUID, ProviderAdapterPort],
    credential_refs: MutableMapping[UUID, str],
) -> None:
    manifest = _echo_manifest()
    provider = Provider(
        id=uuid4(),
        provider_key="local_echo",
        display_name="Local Echo (hermetic)",
        status=ProviderStatus.ACTIVE,
        auth_types=[AuthType.API_KEY],
        supports_account_pool=False,
    )
    providers.register(provider, manifest)
    model = _model("local-echo-1", tier=ModelTier.MEDIUM)
    models.register(model)
    bindings.register(
        ProviderModelBinding(
            provider_id=provider.id,
            model_id=model.id,
            provider_model_name="local-echo-1",
            availability=BindingAvailability.AVAILABLE,
        )
    )
    adapters[provider.id] = LocalEchoAdapter(manifest)
    credential_refs[provider.id] = "secret-ref://local-echo"


def build_runtime_profile(
    environ: Mapping[str, str] | None = None,
) -> RuntimeProfile:
    """Compose the whole platform from the environment (P-B Option A).

    ``environ`` is injectable for hermetic tests; production callers pass
    nothing and get ``os.environ`` — the same convention every
    ``*_from_env`` helper in this package already follows.
    """
    env: Mapping[str, str] = os.environ if environ is None else environ
    env_dict = dict(env)

    # --- registries (ONE set of instances — the instance-agreement duty) ----
    providers = ProviderRegistry()
    models = ModelRegistry()
    binding_registry = BindingRegistry()
    adapters: dict[UUID, ProviderAdapterPort] = {}
    credential_refs: dict[UUID, str] = {}

    provider_keys = _bind_real_providers(
        env, providers, models, binding_registry, adapters, credential_refs
    )
    if not provider_keys:
        _bind_echo_provider(providers, models, binding_registry, adapters, credential_refs)
        provider_keys = ["local_echo"]

    # --- usage / audit / evaluations (in-memory across both profiles for the
    # control plane; durable usage remains a later binding — honest scope) ----
    usage = InMemoryUsageAccounting()
    audit = InMemoryAuditLog()
    evaluations = InMemoryEvaluationStore()

    # --- routing + execution (the SAME instances everywhere) -----------------
    router = SimpleScoringRouter(providers, models, binding_registry)
    execution_service = ExecutionService(
        adapters=adapters,
        credential_refs=credential_refs,
        bindings=binding_registry,
        usage=usage,
        max_retries_per_candidate=_provider_retries(env_dict),
    )

    # --- durable branch (DATABASE_URL) ---------------------------------------
    settings = database_settings_from_env(env_dict)
    durable = settings is not None
    bridge: AsyncBridge | None = None
    bindings: DatabaseBindings | None = None
    identity: IdentityServicePort | None = None
    demo_principal: Principal | None = None

    hasher = Argon2idPasswordHasher()
    email_sender = ConsoleEmailSender()
    admin_emails = frozenset(
        e.strip().lower() for e in env.get(_ENV_ADMIN_EMAILS, "").split(",") if e.strip()
    )

    # --- gateway binding (G2) + platform secret custody for route tokens ----
    # Half-configured gateway raises loudly inside gateway_settings_from_env;
    # absent GATEWAY_BASE_URL ⇒ None ⇒ the onboarding route stays absent
    # (20 §4 — optional seam, nothing to probe). The InMemorySecretManager is
    # the same honest dev custody the real-provider env keys use; production
    # secret custody is the Vault binding (ADR-0007) — swapped HERE only.
    gateway_settings = gateway_settings_from_env(env_dict)
    onboarding_secrets = InMemorySecretManager()

    store: ExecutionStorePort
    idempotency: IdempotencyPort
    if settings is not None:
        bridge = AsyncBridge()
        bindings = build_database_bindings(settings)
        plan_id = ensure_default_plan(bindings, bridge)
        # Gap 1b hydration: replay durably onboarded gateway providers into
        # the SAME registries/maps composed above (the ExecutionService and
        # Router hold references to these exact instances — mutations are
        # immediately visible). Without gateway settings the DATA hydrates
        # but adapters stay honestly absent (AdapterNotBound on routing).
        hydrated_keys = hydrate_gateway_providers(
            database=bindings,
            bridge=bridge,
            providers=providers,
            models=models,
            bindings=binding_registry,
            adapters=adapters,
            credential_refs=credential_refs,
            gateway_settings=gateway_settings,
            secrets=onboarding_secrets,
        )
        provider_keys = [*provider_keys, *hydrated_keys]
        # Gap 2 read side: replay durably persisted admin status flips onto
        # the SAME registries (natural-key match; AFTER gateway hydration so
        # onboarded providers get their overrides too). Without this the
        # write-through above would be write-only — dishonest durability.
        replay_admin_status_overrides(
            database=bindings,
            bridge=bridge,
            providers=providers,
            models=models,
        )
        store = build_durable_execution_store(bindings, bridge)
        identity = BudgetGrantingIdentity(
            inner=build_durable_identity_service(
                bindings,
                bridge,
                hasher=hasher,
                email_sender=email_sender,
                default_plan_id=plan_id,
            ),
            usage=usage,
        )
        proposals, snapshots = build_durable_sourcechange_stores(bindings, bridge)
        # Closure GAP 1: the EXISTING V5 repositories (DatabaseBindings
        # composed them since migration 0002) reach the /v1/workspaces +
        # /v1/projects routes — bridged, same loop-affinity posture.
        workspace_store, project_store = build_durable_workspace_stores(bindings, bridge)
        # Loop affinity (recorded): the pool lives on the bridge loop —
        # server-loop callers (execute route, relay, worker) cross over.
        outbox: OutboxPort = BridgedOutbox(inner=bindings.outbox, bridge=bridge)
        idempotency = BridgedIdempotency(inner=bindings.idempotency, bridge=bridge)
    else:
        store = InMemoryExecutionStore()
        # Same BudgetGrantingIdentity posture as the durable branch (recorded
        # decision 5, symmetric): an admin/user registering in the in-memory
        # profile (e.g. to reach the /admin console) gets the composition-data
        # default budget too — without it the agent's reasoning execution is
        # refused (EntitlementNotConfigured; proven live in the handoff
        # review). The demo principal keeps its explicit grant below.
        identity = BudgetGrantingIdentity(
            inner=InMemoryIdentityService(
                hasher=hasher,
                email_sender=email_sender,
                default_plan_id=DEFAULT_PLAN_ID,
            ),
            usage=usage,
        )
        proposals, snapshots = None, None
        # In-memory profile: create_app's own in-memory defaults serve
        # the same /v1/workspaces + /v1/projects surface (store posture).
        workspace_store, project_store = None, None
        outbox = InMemoryOutbox()
        idempotency = InMemoryIdempotencyStore()
        # Local convenience: one demo principal with a budget so the API
        # is exercisable without registering (composition DATA, in-memory
        # profile ONLY — the durable profile always authenticates).
        demo_principal = Principal(tenant_id=uuid4(), user_id=uuid4())

    # P-D.1: registration admission control is composition DATA — same
    # env posture as EXECUTE_RATE_LIMIT (0 ⇒ disabled, byte-identical).
    auth = AuthSurface(
        identity=identity,
        admin_emails=admin_emails,
        audit=audit,
        rate_limits=InMemoryRateLimiter(),
        register_rate_limit=int(env.get("REGISTER_RATE_LIMIT", "0") or "0"),
    )

    # --- budgets (composition DATA; recorded decision 5) ---------------------
    if demo_principal is not None:
        usage.configure_tenant(
            demo_principal.tenant_id,
            plan=DEFAULT_PLAN_NAME,
            task_units_limit=DEFAULT_TASK_UNITS,
        )

    # --- R160: the SHARED agent runtime + offered catalog ---------------------
    # ONE authority chain (ToolRegistry → CapabilityFirewall → DeviceRegistry)
    # over the SAME router/execution/audit/usage/store. Read-only source tools
    # appear ONLY when AGENT_SOURCE_ROOT is a directory (mandate §9 jail).
    repo_reader = _source_reader(env.get("AGENT_SOURCE_ROOT", ""))
    # ADR-0012: the SHARED engineering capability (workspace/commands/git),
    # opt-in by AGENT_WORKSPACE_ROOT; §14 guard refuses the platform's own
    # checkout at boot. Same registry, same firewall, same audit log.
    engineering = build_engineering(env, audit=audit)
    composed_agent = build_agent(
        router=router,
        execution_service=execution_service,
        store=store,
        audit=audit,
        usage=usage,
        repo_reader=repo_reader,
        engineering=engineering.bundle if engineering is not None else None,
        max_steps=_agent_cap(
            env.get(_ENV_AGENT_MAX_STEPS),
            default=DEFAULT_AGENT_MAX_STEPS,
            low=1,
            high=MAX_AGENT_MAX_STEPS,
        ),
        deadline_ms=_agent_cap(
            env.get(_ENV_AGENT_DEADLINE_MS),
            default=DEFAULT_AGENT_DEADLINE_MS,
            low=1_000,
            high=3_600_000,
        ),
        reasoning_max_tokens=_agent_cap(
            env.get(_ENV_AGENT_REASONING_MAX_TOKENS),
            default=DEFAULT_REASONING_MAX_TOKENS,
            low=MIN_REASONING_MAX_TOKENS,
            high=MAX_REASONING_MAX_TOKENS,
        ),
    )

    def _admit_tenant(tenant_id: UUID) -> None:
        grant_agent_tenant(composed_agent.firewall, tenant_id)
        if engineering is not None:
            # Reads by permission; WRITES stay an Admin decision (grants seam).
            grant_engineering_reads(composed_agent.firewall, tenant_id)

    if demo_principal is not None:
        _admit_tenant(demo_principal.tenant_id)
    if isinstance(identity, BudgetGrantingIdentity):
        identity.on_tenant.append(_admit_tenant)
    engineering_admin = (
        EngineeringAdminSurface(
            bundle=engineering.bundle,
            firewall=composed_agent.firewall,
            remote=engineering.remote,
            commands=engineering.commands,
            grant_writes=grant_engineering_writes,
            audit=audit,
        )
        if engineering is not None
        else None
    )

    # --- admin surface (same instances; router doubles as RoutingWeightsPort) -
    admin_service = AdminConfigService(
        providers=providers,
        models=models,
        usage=usage,
        routing=router,
        audit_log=audit,
        # REGISTER_MODEL binding seam — the SAME BindingRegistry the Router
        # and ExecutionService read (instance-agreement duty).
        bindings=binding_registry,
        # Gap 2: on the durable profile every published/rolled-back admin
        # change writes through to the entity catalogs (the SAME
        # CatalogPersistence doorway the onboarding walker uses — one
        # persistence object, no forked durable behavior). In-memory
        # profile leaves the seam unbound (store posture).
        persistence=(
            CatalogPersistence(bindings, bridge)
            if bindings is not None and bridge is not None
            else None
        ),
    )
    admin = AdminSurface(
        service=admin_service,
        providers=providers,
        models=models,
        usage=usage,
        routing=router,
        evaluations=evaluations,
        audit=audit,
        # R160: USG-2 drill-down (GET /v1/admin/usage) over the SAME execution
        # store the API writes — one derivation, two consumers.
        executions=store,
    )

    # R160: SYS-1 read-model (GET /v1/admin/system) — process-local facts only,
    # every value is composition DATA already in hand (41 §49: no fleet claims).
    def _system_info() -> dict[str, object]:
        return {
            "profile": "durable" if durable else "in-memory",
            "identity_mode": "auth" if demo_principal is None else "hybrid",
            "provider_keys": list(provider_keys),
            "admin_emails_configured": len(admin_emails),
        }

    # --- context composition (13 §5) — same registry/store instances ---------
    conversations = InMemoryConversationStore()
    memory_store = InMemoryMemoryStore()
    roles = RoleRegistry()
    skills = SkillRegistry()
    composer = ContextComposer(memory_store, conversations, roles)

    # --- the app (injection only — env never crosses this line) --------------
    app = create_app(
        router=router,
        execution_service=execution_service,
        store=store,
        # R160 HYBRID identity in the in-memory profile: the demo principal
        # serves header-less calls (zero-config posture kept), while a Bearer
        # session resolves a REAL user — so ADMIN_EMAILS reaches EVERY
        # /v1/admin/* route (not only the console's own) and /v1/auth/* is
        # mounted for the console's login. Durable profile: auth only.
        principal=demo_principal,
        auth=auth,
        system_info=_system_info,
        skills=skills,
        roles=roles,
        conversations=conversations,
        memory=memory_store,  # R158: learning GOLD knowledge substrate (P1)
        composer=composer,
        admin=admin,
        models=models,
        bindings=binding_registry,
        usage=usage,
        webhooks=True,
        rate_limits=InMemoryRateLimiter(),
        execute_rate_limit=int(env.get("EXECUTE_RATE_LIMIT", "0") or "0"),
        outbox=outbox,
        execute_stream=EXECUTE_STREAM,
        healthz=True,
        sse=True,
        source_proposals=proposals,
        workspaces=workspace_store,
        projects=project_store,
        source_snapshots=snapshots,
        agent=composed_agent.surface,
        engineering_admin=engineering_admin,
    )

    # --- admin console (P-D follow-up): the EXISTING attach_admin_console
    # over the SAME already-composed instances — nothing rebuilt, nothing
    # new. /v1/agent + /v1/admin/notifications + the /admin static shell
    # become part of the local runtime in BOTH profiles. The optional V7
    # seams are read back from app.state (the recorded "one derivation,
    # two consumers" duty — create_app derived them; we hand the SAME
    # objects to the agent). R160: the external skill acquisition pipeline
    # (14 §3 import → scan → validate → review → approve → activate) is
    # composed over the SAME SkillRegistry the /v1/execute skill admission
    # and /v1/skills listing read — an ACTIVATED import becomes selectable
    # (and its requires_tools disclosed to the agent) with no second
    # registry and no new permission system.
    attach_admin_console(
        app,
        skill_review=SkillReviewSurface(importing=SkillImportService(), registry=skills),
        surface=AgentToolSurface(
            providers=providers,
            models=models,
            router=router,
            execution_service=execution_service,
            execution_store=store,
            admin=admin,
            usage=usage,
            audit=audit,
            capabilities=app.state.capability_catalog,
            exercise=app.state.exercise_surface,
            scenarios=app.state.scenario_service,
            context_lab=app.state.context_lab_service,
            learning_observability=app.state.learning_observability_service,
            self_review=app.state.self_review_service,
            # Mandate §9 — bounded read-only source inspection. Opt-in by
            # env: AGENT_SOURCE_ROOT names the directory the agent may
            # inspect (jailed, denylisted, byte/entry-capped by the
            # SourceReader itself). Absent/invalid ⇒ absent tools (P2).
            repo_reader=repo_reader,
        ),
        auth=auth,
        # Gap 1c: the onboarding route exists ONLY when the gateway binding
        # is configured (canonical-gateway providers only — DECISION 2;
        # foreign/native-API providers still require an adapter/shim).
        # Absent gateway ⇒ absent route (20 §4).
        provider_onboarding=(
            build_onboarding_surface(
                providers=providers,
                models=models,
                bindings=binding_registry,
                adapters=adapters,
                credential_refs=credential_refs,
                gateway_settings=gateway_settings,
                secrets=onboarding_secrets,
                database=bindings,
                bridge=bridge,
            )
            if gateway_settings is not None
            else None
        ),
        # R160: Admin reasons through the platform's ONE shared agent runtime.
        runtime=composed_agent.surface.runtime,
    )

    # --- end-user UI (P-D.2): the PROVEN ui/admin StaticFiles posture -----
    # Static shell mounted at /app AFTER every API route exists (mount is
    # additive; no route shadowing — /v1/* and /healthz stay untouched).
    # Absent directory ⇒ no mount at all, never a broken route (20 §4).
    if UI_APP_DIR.is_dir():
        app.mount(
            "/app",
            StaticFiles(directory=str(UI_APP_DIR), html=True),
            name="end_user_ui",
        )

    # --- worker + relay (caller-driven bodies; main.py owns cadence) ---------
    queue = InMemoryQueue()

    def _service_factory(execution_id: UUID) -> ExecutionService:
        return ExecutionService(
            adapters=adapters,
            credential_refs=credential_refs,
            bindings=binding_registry,
            usage=usage,
            id_factory=lambda: execution_id,
        )

    handler = ExecutionMessageHandler(
        router=router,
        service_factory=_service_factory,
        store=store,
    )
    worker = Worker(
        queue,
        idempotency,
        stream=EXECUTE_STREAM,
        group=WORKER_GROUP,
        consumer=WORKER_CONSUMER,
        handler=handler,
    )
    relay = OutboxRelay(outbox, queue)

    return RuntimeProfile(
        app=app,
        worker=worker,
        relay=relay,
        outbox=outbox,
        identity=identity,
        usage=usage,
        providers=providers,
        models=models,
        bindings_registry=binding_registry,
        durable=durable,
        bridge=bridge,
        bindings=bindings,
        demo_principal=demo_principal,
        provider_keys=tuple(provider_keys),
        agent=composed_agent,
        adapters=adapters,
    )
