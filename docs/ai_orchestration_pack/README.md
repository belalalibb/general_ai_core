# AI Orchestration Platform — Documentation & Conversation Archive

هذه الحزمة تحتوي على كل ما تم استخراجه وتجهيزه من المحادثة الأصلية والنقاشات اللاحقة حول مشروع **General AI Core / AI Orchestration Platform**.

> هذا الملف هو نقطة الدخول داخل حزمة الوثائق. الملف الرئيسي في جذر الريبو `README.md` يحتوي على Prompt كامل لإعادة هندسة الوثائق ومراجعتها وتحسينها بدون تعقيد زائد.

---

## المحتويات

```text
docs/ai_orchestration_pack/
├── README.md
├── FINAL_PACKAGE_OVERVIEW.md
├── DESIGN_OPINIONS_AND_SUGGESTIONS.md
├── CURRENT_SESSION_DECISIONS.md
├── final_docs_v2/
│   ├── 00_INDEX.md
│   ├── ...
│   └── 21_PROVIDER_AGENT_ORCHESTRATION_SPEC.md
├── source_materials/
│   └── rev_prompt_original.txt
└── conversation_archive/
    ├── original_shared_chat_raw.html
    ├── original_shared_chat_react_stream.txt
    └── original_shared_conversation_extracted.md
```

---

## أهم ملف تبدأ منه

ابدأ من:

```text
../../README.md
final_docs_v2/00_INDEX.md
```

ثم استخدم:

```text
final_docs_v2/20_ULTRA_EXECUTION_PROMPT.md
```

عند تشغيل Agent للتنفيذ أو المراجعة بأقصى جودة.

واستخدم بروتوكول الاستئناف الخفيف:

```text
final_docs_v2/22_LIGHTWEIGHT_RESUME_AND_PROGRESS_STATE_PROTOCOL.md
```

---

## قاعدة الاستئناف الثابتة

هذه القاعدة لا تُحذف ولا تُخفف. الاستئناف لازم يكون قليل التوكن، لكنه صارم ويحافظ على حالة التقدم عند فقدان جلسة الشات التي تنفذ المشروع:

```text
Git committed state = trusted progress.
Uncommitted work = recovery candidate only.
No DONE without verification + commit.
Never trust conversation memory as project truth.
Never delete or reset uncommitted work blindly.
```

عند أي انقطاع جلسة:

```text
git status
↓
git rev-parse HEAD
↓
git diff --stat
↓
inspect filesystem and new files
↓
read README.md and docs index
↓
read compact state / next plan if present
↓
identify last trusted commit
↓
classify uncommitted work
↓
if state was not updated, reconstruct from Git + files + verification
↓
resume smallest valid micro-task
```

---

## Documentation Re-Architecture Mini Prompt

إذا كان الـAgent سيحسن الوثائق، استخدم هذا المختصر، أو استخدم الـPrompt الكامل في جذر الريبو:

```text
You are a Documentation Re-Architecture Agent for the General AI Core / AI Orchestration Platform.

Review all docs, source materials, conversation archive, opinions, suggestions, and current decisions.
Your goal is to produce stronger final documentation with less unnecessary complexity.

Do not build product code.
Do not distract the project with unrelated modules.
Do not add features unless they improve execution value.

Preserve:
- provider/model/account separation
- router/execution separation
- capability firewall
- tenant isolation
- user-owned credentials
- full model control
- provider-native agents as subordinate sub-agents
- evaluation/learning governance
- admin control plane
- strict Git-based resume protocol

Before editing:
1. git status
2. git rev-parse HEAD
3. git diff
4. inspect uncommitted changes
5. read README.md
6. read final_docs_v2/00_INDEX.md

Improve by:
- removing duplication
- resolving contradictions
- adding missing acceptance criteria
- adding safeguards against lazy or unsafe implementation
- simplifying MVP implementation while preserving final contracts
- making resume/recovery rules impossible to miss

After editing:
- summarize changes
- verify consistency
- commit
- verify commit
- write next micro-task
```

---

## ملاحظة مهمة

المحادثة الأصلية محفوظة كـHTML خام وكتفريغ نصي best-effort. الوثائق النهائية في `final_docs_v2` هي النسخة التنفيذية المنظمة، وليست مجرد نسخ حرفي للحوار.
