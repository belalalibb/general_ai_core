"""
سجلّ مفاتيح مركزي للـ Gateway (النسخة الموحّدة NEW design).

مبدأ حاسم: لا طريق جانبي يسمح باستنتاج المزوّد من الـ request. الـ credential
للـ platform mode يُستعلَم بالـ internal slug (الذي فكّه الـ Gateway من route_token
داخليًا) — وليس من أي حقل provider في المظروف (لم يعد موجودًا أصلًا).

    route_token  →  internal route map (app.py)  →  slug  →  credential profile (هنا)

يدير كل المفاتيح من مكان واحد:
- مفتاح واحد يخدم مجموعة مزوّدين (نمط مشترك).
- أو مفتاح مختلف لكل مزوّد.
كل ذلك داخل الـ Gateway فقط — المنصة لا تعرف ولا تتأثر.
"""
from __future__ import annotations

import os

# -------------------------------------------------------------------------
# مجموعات مفاتيح مشتركة: اسم متغيّر البيئة -> الـ slugs الداخلية التي تستخدمه.
# -------------------------------------------------------------------------
_SHARED_KEY_GROUPS: dict[str, tuple[str, ...]] = {
    "MASTER_LLM_KEY": ("my_llm", "my_gpt", "my_chat"),
    "MY_VISION_KEY":  ("my_vision",),
}


def resolve_platform_credential(slug: str) -> str | None:
    """أرجع مفتاح الـ platform لهذا المزوّد بالـ internal slug فقط.

    الأولوية:
      1. مجموعة مفتاح مشترك.
      2. مفتاح مخصّص <SLUG>_PLATFORM_KEY.
      3. None ⇒ الـ handler يرجّع err("invalid_credential", ...).

    ملاحظة: المدخل هو الـ slug الداخلي (من route map)، لا أي قيمة من الـ request.
    """
    for env_var, members in _SHARED_KEY_GROUPS.items():
        if slug in members:
            key = os.environ.get(env_var)
            if key:
                return key
    return os.environ.get(f"{slug.upper()}_PLATFORM_KEY")
