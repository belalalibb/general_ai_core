# Current Session Decisions

هذه الوثيقة تلخص القرارات التي أضيفت بعد مراجعة الوثائق الأولية.

---

## D1. إعادة كتابة الوثائق كـEngineering Specification Pack

تم إنشاء `final_docs_v2` كحزمة أقوى من النسخة الأولى، تشمل 22 ملفًا من `00_INDEX.md` حتى `21_PROVIDER_AGENT_ORCHESTRATION_SPEC.md`.

---

## D2. إضافة Cognitive Operating Protocol

تمت إضافة:

```text
19_AGENT_COGNITIVE_OPERATING_PROTOCOL.md
```

لإجبار الـAgent على:

```text
تصنيف المهمة
اختيار عمق التفكير
مقارنة البدائل
عمل Red-Team
منع overengineering
إثبات النجاح بالدليل
```

---

## D3. إضافة Ultra Execution Prompt

تمت إضافة:

```text
20_ULTRA_EXECUTION_PROMPT.md
```

لاستخدامه عند تنفيذ المراحل الحرجة بأقصى جودة.

---

## D4. التحكم الكامل في اختيار النماذج

تم تحديث:

```text
04_API_CONTRACTS.md
06_MODEL_ROUTING_SPEC.md
07_EXECUTION_GRAPH_SPEC.md
11_ADMIN_CONTROL_PLANE_SPEC.md
18_QA_DECISION_LOG.md
```

لدعم:

```text
AUTO
TIER
EXPLICIT_MODEL
EXPLICIT_MODELS
AGENT_NODE_MAPPING
```

---

## D5. توضيح أن النموذج قد يكون Agent داخل مزود

تم تحديث الوثائق لتوضيح:

```text
Provider Agent Capability ≠ Platform Agent Runtime
```

---

## D6. Orchestration لأكثر من Provider Agent داخل Agent المنتج

تمت إضافة:

```text
21_PROVIDER_AGENT_ORCHESTRATION_SPEC.md
```

لتثبيت أن Agent المنتج الأساسي يمكنه استخدام عدة provider-native agents كـsub-agents/specialist nodes داخل Execution Graph واحد.
