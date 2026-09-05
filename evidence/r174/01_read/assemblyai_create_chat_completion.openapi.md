> ## Documentation Index
> Fetch the complete documentation index at: https://assemblyai.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# Create a chat completion

> 

<Note>To use our EU server for LLM Gateway, replace `llm-gateway.assemblyai.com` with `llm-gateway.eu.assemblyai.com`.</Note>

Generates a response from a model given a prompt or a series of messages.



## OpenAPI

````yaml api-reference/specs/llm-gateway.yaml POST /chat/completions
openapi: 3.1.0
info:
  title: AAI Chat Completions API
  description: API for generating text with various language models.
  version: 1.0.0
servers:
  - url: https://llm-gateway.assemblyai.com/v1
    description: Production Server
    x-fern-server-name: Production
security:
  - ApiKey: []
paths:
  /chat/completions:
    post:
      summary: Create a chat completion
      description: >-


        <Note>To use our EU server for LLM Gateway, replace
        `llm-gateway.assemblyai.com` with
        `llm-gateway.eu.assemblyai.com`.</Note>


        Generates a response from a model given a prompt or a series of
        messages.
      operationId: createChatCompletion
      requestBody:
        description: Request body for creating a chat completion.
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/LLMGatewayRequest'
            examples:
              messages_example:
                summary: Chat with messages
                value:
                  model: qwen3.5-4b-32k-fast
                  messages:
                    - role: user
                      content: Hello, how are you?
                  max_tokens: 100
                  temperature: 0.7
              prompt_example:
                summary: Simple prompt
                value:
                  model: qwen3.5-4b-32k-fast
                  prompt: Write a haiku about coding
                  max_tokens: 50
                  temperature: 0.5
              transcript_id_example:
                summary: Inject a transcript by ID
                value:
                  model: gemini-2.5-flash-lite
                  messages:
                    - role: user
                      content: hi there
                    - role: assistant
                      content: Hi! How can I help?
                    - role: user
                      content: >-
                        Here is a transcript: {{ transcript }}. Return the text
                        verbatim.
                  transcript_id: 065a71ac-dc3e-4e38-9374-e54c0bea564f
              structured_output_example:
                summary: Structured output with JSON schema
                value:
                  model: gemini-2.5-flash-lite
                  messages:
                    - role: system
                      content: >-
                        You are a helpful math tutor. Guide the user through the
                        solution step by step.
                    - role: user
                      content: how can I solve 8x + 7 = -23
                  response_format:
                    type: json_schema
                    json_schema:
                      name: math_reasoning
                      schema:
                        type: object
                        properties:
                          steps:
                            type: array
                            items:
                              type: object
                              properties:
                                explanation:
                                  type: string
                                output:
                                  type: string
                              required:
                                - explanation
                                - output
                              additionalProperties: false
                          final_answer:
                            type: string
                        required:
                          - steps
                          - final_answer
                        additionalProperties: false
                      strict: true
              post_processing_example:
                summary: JSON repair post-processing
                value:
                  model: gemini-2.5-flash-lite
                  messages:
                    - role: user
                      content: Extract the user name and return as JSON
                  post_processing_steps:
                    - type: json-repair
      responses:
        '200':
          description: Successful response containing the model's choices.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Response'
        default:
          description: An unexpected error occurred.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
components:
  schemas:
    LLMGatewayRequest:
      type: object
      description: The main request body for the chat completions endpoint.
      properties:
        messages:
          type: array
          items:
            $ref: '#/components/schemas/Message'
          description: A list of messages comprising the conversation so far.
        prompt:
          type: string
          description: >-
            A simple string prompt. The API will automatically convert this into
            a user message.
        transcript_id:
          type: string
          description: >
            Optional. The ID of an AssemblyAI transcript whose text replaces the
            first `{{ transcript }}` tag in the prompt. See [Inject a transcript
            by
            ID](https://www.assemblyai.com/docs/llm-gateway/chat-completions#inject-a-transcript-by-id)
            for substitution rules and edge cases.
          examples:
            - 065a71ac-dc3e-4e38-9374-e54c0bea564f
        model:
          type: string
          description: >-
            The ID of the model to use for this request. See [LLM Gateway
            Overview](https://www.assemblyai.com/docs/llm-gateway/quickstart#available-models)
            for available models.
          examples:
            - claude-sonnet-4-5-20250929
        model_region:
          type: string
          enum:
            - global
          description: >
            Optional. Routes the request to the provider's global (non-region)
            endpoints for lower-cost processing. The only accepted value is
            `global`; omit this field for default in-region processing.
            Currently live for Anthropic Claude models, with Google Gemini 3
            series coming soon.
          examples:
            - global
        max_tokens:
          type: integer
          minimum: 1
          default: 1000
          description: >-
            The maximum number of tokens to generate in the completion. Default
            is 1000.
        temperature:
          type: number
          format: float
          minimum: 0
          maximum: 2
          description: >-
            Controls randomness. Lower values produce more deterministic
            results.
        stream:
          type: boolean
          default: false
          description: >-
            When true, responses are streamed as server-sent events (SSE).
            Supported on OpenAI models only.
        tools:
          type: array
          items:
            $ref: '#/components/schemas/Tool'
          description: A list of tools the model may call.
        tool_choice:
          $ref: '#/components/schemas/ToolChoice'
        response_format:
          $ref: '#/components/schemas/ResponseFormat'
          description: >-
            Specifies the format of the model's response. Use this to constrain
            the model to output valid JSON matching a schema. Supported by
            OpenAI (GPT-4.1, GPT-5.x), Gemini, and Claude models. Not supported
            by gpt-oss models.
        fallbacks:
          type: array
          items:
            $ref: '#/components/schemas/FallbackObject'
          description: >-
            An array of fallback objects. Each object must include a `model` and
            can optionally override any field from the original request. If the
            primary model fails, the LLM Gateway tries each fallback in order
            until one succeeds. See [Specify fallback
            models](https://www.assemblyai.com/docs/llm-gateway/fallback) for
            more details.
        fallback_config:
          $ref: '#/components/schemas/FallbackConfig'
          description: >-
            Configuration for fallback behavior, including retry and depth
            settings. See [Specify fallback
            models](https://www.assemblyai.com/docs/llm-gateway/fallback) for
            more details.
        post_processing_steps:
          type: array
          items:
            $ref: '#/components/schemas/PostProcessingStep'
          description: >
            An ordered list of post-processing steps to apply to the model's
            response after generation. Currently supports `json-repair`, which
            automatically fixes malformed JSON in LLM Gateway content responses.
            See
            [Post-processing](https://www.assemblyai.com/docs/llm-gateway/structured-outputs#post-processing)
            for details.
      required:
        - model
    Response:
      type: object
      properties:
        request_id:
          type: string
          format: uuid
        choices:
          type: array
          items:
            $ref: '#/components/schemas/Choice'
        request:
          type: object
          description: A copy of the original request, excluding `prompt` and `messages`.
          properties:
            model:
              type: string
            max_tokens:
              type: integer
            temperature:
              type: number
            tools:
              type: array
              items:
                $ref: '#/components/schemas/Tool'
            tool_choice:
              $ref: '#/components/schemas/ToolChoice'
        usage:
          $ref: '#/components/schemas/Usage'
        http_status_code:
          type: integer
          description: The HTTP status code of the response
          example: 200
        response_time:
          type: integer
          description: The response time in nanoseconds
          example: 275510459
        llm_status_code:
          type: integer
          description: The status code from the LLM provider
          example: 200
    ErrorResponse:
      type: object
      properties:
        code:
          type: integer
          format: int32
          description: HTTP status code for the error.
        message:
          type: string
          description: A human-readable description of the error.
        request_id:
          type: string
          format: uuid
          description: Unique identifier for the request.
        metadata:
          type: object
          description: >-
            Optional. Present on 400 responses with per-field validation
            details.
          properties:
            errors:
              type: array
              items:
                type: string
              description: List of specific validation failure messages.
      required:
        - code
        - message
        - request_id
    Message:
      oneOf:
        - $ref: '#/components/schemas/UserAssistantSystemMessage'
        - $ref: '#/components/schemas/ToolMessage'
      discriminator:
        propertyName: role
        mapping:
          user:
            $ref: '#/components/schemas/UserAssistantSystemMessage'
          assistant:
            $ref: '#/components/schemas/UserAssistantSystemMessage'
          system:
            $ref: '#/components/schemas/UserAssistantSystemMessage'
          tool:
            $ref: '#/components/schemas/ToolMessage'
    Tool:
      type: object
      properties:
        type:
          type: string
          enum:
            - function
        function:
          $ref: '#/components/schemas/FunctionDescription'
      required:
        - type
        - function
    ToolChoice:
      oneOf:
        - type: string
          enum:
            - none
            - auto
        - type: object
          properties:
            type:
              type: string
              enum:
                - function
            function:
              type: object
              properties:
                name:
                  type: string
              required:
                - name
          required:
            - type
            - function
      description: Controls which (if any) function is called by the model.
    ResponseFormat:
      type: object
      description: >-
        Specifies the format of the model's response. Use `json_schema` type to
        constrain the model to output valid JSON matching a schema.
      properties:
        type:
          type: string
          enum:
            - json_schema
          description: >-
            The type of response format. Use `json_schema` for structured
            outputs.
        json_schema:
          $ref: '#/components/schemas/JsonSchemaConfig'
          description: The JSON schema configuration object.
      required:
        - type
        - json_schema
    FallbackObject:
      type: object
      description: >-
        A fallback model configuration. Each object must include a `model` and
        can optionally override any field from the original request. Fields not
        specified in the fallback inherit the values from the original request.
        See [Specify fallback
        models](https://www.assemblyai.com/docs/llm-gateway/fallback) for more
        details.
      properties:
        model:
          type: string
          description: >-
            The fallback model to use. See [LLM Gateway
            Overview](https://www.assemblyai.com/docs/llm-gateway/quickstart#available-models)
            for available models.
          examples:
            - claude-sonnet-4-6
        messages:
          type: array
          items:
            $ref: '#/components/schemas/Message'
          description: Override the messages for the fallback request.
        max_tokens:
          type: integer
          minimum: 1
          description: >-
            Override the maximum number of tokens to generate in the fallback
            completion.
        temperature:
          type: number
          format: float
          minimum: 0
          maximum: 2
          description: Override the temperature for the fallback request.
      additionalProperties: true
      required:
        - model
    FallbackConfig:
      type: object
      description: >-
        Configuration for fallback behavior. See [Specify fallback
        models](https://www.assemblyai.com/docs/llm-gateway/fallback) for more
        details.
      properties:
        retry:
          type: boolean
          default: true
          description: >-
            Whether to automatically retry the request once after 500ms on
            failure. Defaults to `true`.
        depth:
          type: integer
          minimum: 1
          maximum: 2
          default: 1
          description: >-
            The maximum number of fallbacks to traverse. Defaults to `1`, with a
            maximum of `2`.
    PostProcessingStep:
      type: object
      description: A single post-processing operation to apply to the model's response.
      properties:
        type:
          type: string
          enum:
            - json-repair
          description: >-
            The type of post-processing to apply. Currently `json-repair` is
            supported.
      required:
        - type
    Choice:
      type: object
      properties:
        message:
          $ref: '#/components/schemas/ResponseMessage'
        finish_reason:
          type: string
          description: The reason the model stopped generating tokens.
          examples:
            - stop
    Usage:
      type: object
      properties:
        input_tokens:
          type: integer
        output_tokens:
          type: integer
        total_tokens:
          type: integer
      required:
        - input_tokens
        - output_tokens
        - total_tokens
    UserAssistantSystemMessage:
      type: object
      properties:
        role:
          type: string
          enum:
            - user
            - assistant
            - system
        content:
          oneOf:
            - type: string
            - type: array
              items:
                $ref: '#/components/schemas/ContentPart'
          description: >-
            The content of the message. Can be a string or an array of content
            parts (for user messages).
        name:
          type: string
          description: An optional name for the participant.
      required:
        - role
        - content
    ToolMessage:
      type: object
      properties:
        role:
          type: string
          enum:
            - tool
        content:
          type: string
          description: The result of the tool call.
        tool_call_id:
          type: string
          description: The ID of the tool call that this message is responding to.
      required:
        - role
        - content
        - tool_call_id
    FunctionDescription:
      type: object
      properties:
        name:
          type: string
          description: The name of the function to be called.
        description:
          type: string
          description: A description of what the function does.
        parameters:
          type: object
          description: A JSON Schema object describing the parameters the function accepts.
          additionalProperties: true
      required:
        - name
        - parameters
    JsonSchemaConfig:
      type: object
      description: Configuration for JSON schema-based structured outputs.
      properties:
        name:
          type: string
          description: A name for the schema. Used for identification purposes.
        schema:
          type: object
          description: >-
            A valid JSON Schema object that defines the structure of the
            expected response.
          additionalProperties: true
        strict:
          type: boolean
          description: >-
            When `true`, the model will strictly adhere to the schema.
            Recommended for reliable parsing.
          default: false
      required:
        - name
        - schema
    ResponseMessage:
      type: object
      properties:
        role:
          type: string
        content:
          type: string
          nullable: true
          description: >-
            The text content of the model's response. Null or empty when the
            model is only emitting tool_calls.
        tool_calls:
          type: array
          items:
            $ref: '#/components/schemas/FunctionToolCall'
    ContentPart:
      $ref: '#/components/schemas/TextContent'
      description: Currently only supports text content parts.
    FunctionToolCall:
      type: object
      properties:
        id:
          type: string
        type:
          type: string
          enum:
            - function
        function:
          $ref: '#/components/schemas/FunctionCall'
      required:
        - id
        - type
        - function
    TextContent:
      type: object
      properties:
        type:
          type: string
          enum:
            - text
        text:
          type: string
      required:
        - type
        - text
    FunctionCall:
      type: object
      properties:
        name:
          type: string
        arguments:
          type: string
          description: The arguments to call the function with, as a JSON-formatted string.
      required:
        - name
        - arguments
  securitySchemes:
    ApiKey:
      type: apiKey
      in: header
      name: Authorization

````