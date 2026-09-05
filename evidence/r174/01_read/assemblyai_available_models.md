> ## Documentation Index
> Fetch the complete documentation index at: https://assemblyai.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# Models

## Available models

| Model                     | ID                           | Supported parameters                                                             | Providers        | Default Provider | Max Context | Retirement Date |
| ------------------------- | ---------------------------- | -------------------------------------------------------------------------------- | ---------------- | ---------------- | ----------- | --------------- |
| **Haiku 4.5**             | `claude-haiku-4-5-20251001`  | `max_tokens`, `temperature`, `tools`, `tool_choice`, `response_format`, `stream` | `Bedrock`        | `Bedrock`        | `200000`    |                 |
| **Opus 4.5**              | `claude-opus-4-5-20251101`   | `max_tokens`, `temperature`, `tools`, `tool_choice`, `response_format`, `stream` | `Bedrock`        | `Bedrock`        | `200000`    |                 |
| **Qwen3.5 4B Fast**       | `qwen3.5-4b-32k-fast`        | `max_tokens`, `temperature`, `stream`                                            | `AssemblyAI`     | `AssemblyAI`     | `32768`     |                 |
| **Opus 4.6**              | `claude-opus-4-6`            | `max_tokens`, `temperature`, `tools`, `tool_choice`, `response_format`, `stream` | `Bedrock`        | `Bedrock`        | `200000`    |                 |
| **Opus 4.7**              | `claude-opus-4-7`            | `max_tokens`, `tools`, `tool_choice`, `stream`                                   | `Bedrock`        | `Bedrock`        | `1000000`   |                 |
| **Opus 4.8**              | `claude-opus-4-8`            | `max_tokens`, `tools`, `tool_choice`, `stream`                                   | `Bedrock`        | `Bedrock`        | `1000000`   |                 |
| **Opus 5**                | `claude-opus-5`              | `max_tokens`, `tools`, `tool_choice`, `stream`                                   | `Bedrock`        | `Bedrock`        | `200000`    |                 |
| **Sonnet 4.5**            | `claude-sonnet-4-5-20250929` | `max_tokens`, `temperature`, `tools`, `tool_choice`, `response_format`, `stream` | `Bedrock`        | `Bedrock`        | `200000`    |                 |
| **Sonnet 4.6**            | `claude-sonnet-4-6`          | `max_tokens`, `temperature`, `tools`, `tool_choice`, `response_format`, `stream` | `Bedrock`        | `Bedrock`        | `200000`    |                 |
| **Sonnet 5**              | `claude-sonnet-5`            | `max_tokens`, `tools`, `tool_choice`, `stream`                                   | `Bedrock`        | `Bedrock`        | `200000`    |                 |
| **Gemini 2.5 Flash**      | `gemini-2.5-flash`           | `max_tokens`, `response_format`, `temperature`, `tools`, `tool_choice`, `stream` | `Vertex`         | `Vertex`         | `1048576`   |                 |
| **Gemini 2.5 Flash Lite** | `gemini-2.5-flash-lite`      | `max_tokens`, `response_format`, `temperature`, `tools`, `tool_choice`, `stream` | `Vertex`         | `Vertex`         | `1048576`   |                 |
| **Gemini 2.5 Pro**        | `gemini-2.5-pro`             | `max_tokens`, `response_format`, `temperature`, `tools`, `tool_choice`, `stream` | `Vertex`         | `Vertex`         | `200000`    |                 |
| **Gemini 3.1 Flash Lite** | `gemini-3.1-flash-lite`      | `max_tokens`, `response_format`, `temperature`, `tools`, `tool_choice`, `stream` | `Vertex`         | `Vertex`         | `1048575`   | 2027-05-07      |
| **Gemini 3.5 Flash**      | `gemini-3.5-flash`           | `max_tokens`, `response_format`, `temperature`, `tools`, `tool_choice`, `stream` | `Vertex`         | `Vertex`         | `1048575`   |                 |
| **Gemini 3.5 Flash Lite** | `gemini-3.5-flash-lite`      | `max_tokens`, `response_format`, `temperature`, `tools`, `tool_choice`, `stream` | `Vertex`         | `Vertex`         | `1048575`   |                 |
| **Gemini 3.6 Flash**      | `gemini-3.6-flash`           | `max_tokens`, `response_format`, `temperature`, `tools`, `tool_choice`, `stream` | `Vertex`         | `Vertex`         | `1048575`   |                 |
| **Gemini 3.7 Flash**      | `gemini-3.7-flash`           | `max_tokens`, `response_format`, `temperature`, `tools`, `tool_choice`, `stream` | `Vertex`         | `Vertex`         | `1048575`   |                 |
| **gemma-4-31b**           | `gemma-4-31b`                | `max_tokens`, `response_format`, `temperature`, `tools`, `tool_choice`, `stream` | `Bedrock Mantle` | `Bedrock Mantle` | `256000`    |                 |
| **GPT OSS 120B**          | `gpt-oss-120b`               | `max_tokens`, `response_format`, `temperature`, `tools`, `tool_choice`           | `Bedrock`        | `Bedrock`        | `131072`    |                 |
| **GPT OSS 20B**           | `gpt-oss-20b`                | `max_tokens`, `temperature`, `tools`, `tool_choice`                              | `Bedrock`        | `Bedrock`        | `131072`    |                 |
| **GPT-4.1**               | `gpt-4.1`                    | `max_tokens`, `temperature`, `tools`, `tool_choice`, `stream`                    | `Open AI`        | `Open AI`        | `1047576`   |                 |
| **GPT-5**                 | `gpt-5`                      | `max_tokens`, `temperature`, `tools`, `tool_choice`, `stream`, `response_format` | `Open AI`        | `Open AI`        | `400000`    |                 |
| **GPT-5 Nano**            | `gpt-5-nano`                 | `max_tokens`, `response_format`, `temperature`, `tools`, `tool_choice`, `stream` | `Open AI`        | `Open AI`        | `400000`    |                 |
| **GPT-5 mini**            | `gpt-5-mini`                 | `max_tokens`, `response_format`, `temperature`, `tools`, `tool_choice`, `stream` | `Open AI`        | `Open AI`        | `400000`    |                 |
| **GPT-5.1**               | `gpt-5.1`                    | `max_tokens`, `response_format`, `temperature`, `tools`, `tool_choice`, `stream` | `Open AI`        | `Open AI`        | `400000`    |                 |
| **GPT-5.2**               | `gpt-5.2`                    | `max_tokens`, `response_format`, `temperature`, `tools`, `tool_choice`, `stream` | `Open AI`        | `Open AI`        | `400000`    |                 |
| **GPT-5.5**               | `gpt-5.5`                    | `max_tokens`, `response_format`, `tools`, `tool_choice`, `stream`                | `Open AI`        | `Open AI`        | `272000`    |                 |
| **GPT-5.6 Luna**          | `gpt-5.6-luna`               | `max_tokens`, `response_format`, `tools`, `tool_choice`, `stream`                | `Open AI`        | `Open AI`        | `270000`    |                 |
| **GPT-5.6 Sol**           | `gpt-5.6-sol`                | `max_tokens`, `response_format`, `tools`, `tool_choice`, `stream`                | `Open AI`        | `Open AI`        | `270000`    |                 |
| **GPT-5.6 Terra**         | `gpt-5.6-terra`              | `max_tokens`, `response_format`, `tools`, `tool_choice`, `stream`                | `Open AI`        | `Open AI`        | `270000`    |                 |
| **Qwen3 32B**             | `qwen3-32B`                  | `max_tokens`, `temperature`, `tools`, `tool_choice`, `response_format`, `stream` | `Bedrock`        | `Bedrock`        | `200000`    |                 |
| **Qwen3 Next 80B A3B**    | `qwen3-next-80b-a3b`         | `max_tokens`, `temperature`, `tools`, `tool_choice`, `response_format`, `stream` | `Bedrock`        | `Bedrock`        | `200000`    |                 |

### Pricing details

| Model                     | Parameter                    | Prompt (per 1M) | Completion (per 1M) | Cache read (per 1M) | Cache write (per 1M) | Cache write 1h (per 1M) | Regional surcharge |
| ------------------------- | ---------------------------- | --------------- | ------------------- | ------------------- | -------------------- | ----------------------- | ------------------ |
| **Haiku 4.5**             | `claude-haiku-4-5-20251001`  | \$1             | \$5                 | \$0.1               | \$1.25               | \$2                     | +10%               |
| **Opus 4.5**              | `claude-opus-4-5-20251101`   | \$5             | \$25                | \$0.5               | \$6.25               | \$10                    | +10%               |
| **Qwen3.5 4B Fast**       | `qwen3.5-4b-32k-fast`        | \$0.1           | \$0.5               |                     |                      |                         |                    |
| **Opus 4.6**              | `claude-opus-4-6`            | \$5             | \$25                | \$0.5               | \$6.25               | \$10                    | +10%               |
| **Opus 4.7**              | `claude-opus-4-7`            | \$5             | \$25                | \$0.5               | \$6.25               | \$10                    | +10%               |
| **Opus 4.8**              | `claude-opus-4-8`            | \$5             | \$25                | \$0.5               | \$6.25               | \$10                    | +10%               |
| **Opus 5**                | `claude-opus-5`              | \$5             | \$25                | \$0.5               | \$6.25               | \$10                    | +10%               |
| **Sonnet 4.5**            | `claude-sonnet-4-5-20250929` | \$3             | \$15                | \$0.3               | \$3.75               | \$6                     | +10%               |
| **Sonnet 4.6**            | `claude-sonnet-4-6`          | \$3             | \$15                | \$0.3               | \$3.75               | \$6                     | +10%               |
| **Sonnet 5**              | `claude-sonnet-5`            | \$3             | \$15                | \$0.3               | \$3.75               | \$6                     | +10%               |
| **Gemini 2.5 Flash**      | `gemini-2.5-flash`           | \$0.3           | \$2.5               | \$0.03              |                      |                         | +10%               |
| **Gemini 2.5 Flash Lite** | `gemini-2.5-flash-lite`      | \$0.1           | \$0.4               | \$0.01              |                      |                         | +10%               |
| **Gemini 2.5 Pro**        | `gemini-2.5-pro`             | \$1.25          | \$10                | \$0.125             |                      |                         | +10%               |
| **Gemini 3.1 Flash Lite** | `gemini-3.1-flash-lite`      | \$0.25          | \$1.5               | \$0.025             |                      |                         | +10%               |
| **Gemini 3.5 Flash**      | `gemini-3.5-flash`           | \$1.25          | \$9                 | \$0.125             |                      |                         | +10%               |
| **Gemini 3.5 Flash Lite** | `gemini-3.5-flash-lite`      | \$0.3           | \$2.5               | \$0.03              |                      |                         | +10%               |
| **Gemini 3.6 Flash**      | `gemini-3.6-flash`           | \$1.5           | \$7.5               | \$0.15              |                      |                         | +10%               |
| **Gemini 3.7 Flash**      | `gemini-3.7-flash`           | \$0.75          | \$3.75              | \$0.075             |                      |                         | +10%               |
| **gemma-4-31b**           | `gemma-4-31b`                | \$0.14          | \$0.4               |                     |                      |                         |                    |
| **GPT OSS 120B**          | `gpt-oss-120b`               | \$0.15          | \$0.6               |                     |                      |                         |                    |
| **GPT OSS 20B**           | `gpt-oss-20b`                | \$0.07          | \$0.3               |                     |                      |                         |                    |
| **GPT-4.1**               | `gpt-4.1`                    | \$2             | \$8                 | \$0.5               |                      |                         | +10%               |
| **GPT-5**                 | `gpt-5`                      | \$1.25          | \$10                | \$0.125             |                      |                         | +10%               |
| **GPT-5 Nano**            | `gpt-5-nano`                 | \$0.05          | \$0.4               | \$0.005             |                      |                         | +10%               |
| **GPT-5 mini**            | `gpt-5-mini`                 | \$0.25          | \$2                 | \$0.025             |                      |                         | +10%               |
| **GPT-5.1**               | `gpt-5.1`                    | \$1.25          | \$10                | \$0.125             |                      |                         | +10%               |
| **GPT-5.2**               | `gpt-5.2`                    | \$1.75          | \$14                | \$0.175             |                      |                         | +10%               |
| **GPT-5.5**               | `gpt-5.5`                    | \$5             | \$30                | \$0.5               |                      |                         | +10%               |
| **GPT-5.6 Luna**          | `gpt-5.6-luna`               | \$1             | \$6                 | \$0.1               | \$1.25               |                         | +10%               |
| **GPT-5.6 Sol**           | `gpt-5.6-sol`                | \$4             | \$20                | \$0.4               | \$5                  |                         | +10%               |
| **GPT-5.6 Terra**         | `gpt-5.6-terra`              | \$2.5           | \$15                | \$0.25              | \$3.125              |                         | +10%               |
| **Qwen3 32B**             | `qwen3-32B`                  | \$0.15          | \$0.6               |                     |                      |                         |                    |
| **Qwen3 Next 80B A3B**    | `qwen3-next-80b-a3b`         | \$0.15          | \$1.2               |                     |                      |                         |                    |

<Note>
  For information on data retention and model training policies for each
  provider, see [Data Retention and Model Training](/docs/data-retention-and-model-training#llm-gateway-production-environment).
</Note>

<Note>
  Head to [our Playground](https://www.assemblyai.com/dashboard/home) to
  test out LLM Gateway without having to write any code!
</Note>
