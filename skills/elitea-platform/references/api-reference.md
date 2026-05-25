# Elitea Platform - API Documentation

> **End-to-end reference for the ELITEA REST API** — covers entity CRUD AND the runtime/conversational surface (conversations, messages, participants, attachments, predict, publish, MCP discovery).
>
> Last Updated: 2026-05-25 — extended with operational API surface, reverse-engineered from `EliteaAI/elitea_core` (`api/v2/*.py`) and cross-validated against `EliteaAI/elitea-api-testing` pytest fixtures.

---

## Table of Contents

**Foundations**
0. [Conventions & Auth](#0-conventions--auth)

**Entity CRUD** (frontend-derived schemas)
1. [Agents (Applications)](#1-agents-applications)
   - [Create Agent](#11-create-agent)
   - [Update Agent Entity](#12-update-agent-entity)
   - [Update Agent Version](#13-update-agent-version)
   - [Create New Version](#14-create-new-version)
2. [Pipelines](#2-pipelines)
   - [Create Pipeline](#21-create-pipeline)
   - [Update Pipeline](#22-update-pipeline)
3. [Toolkits](#3-toolkits)
   - [Create Toolkit](#31-create-toolkit)
   - [Update Toolkit](#32-update-toolkit)
   - [Associate/Disassociate Toolkit](#33-associatedisassociate-toolkit)
4. [Credentials (Configurations)](#5-credentials-configurations)
   - [Create Credential](#51-create-credential)
   - [Update Credential](#52-update-credential)
5. [Secrets](#6-secrets)
   - [Create Secret](#61-create-secret)
   - [Update Secret](#62-update-secret)

**Runtime / Operational API** (v2 source)
6. [Conversations & Folders](#6-conversations--folders)
7. [Participants & Entity Settings](#7-participants--entity-settings)
8. [Messages, Attachments & Canvas](#8-messages-attachments--canvas)
9. [Tool & Toolkit Discovery (incl. MCP)](#9-tool--toolkit-discovery-incl-mcp)
10. [Agent Execution (Predict)](#10-agent-execution-predict)
11. [Lifecycle: Publish / Unpublish / Fork / Import-Export](#11-lifecycle-publish--unpublish--fork--import-export)
12. [Pipeline Triggers & Webhooks](#12-pipeline-triggers--webhooks)

**Reference**
13. [Quick Reference](#13-quick-reference)
14. [Patterns & Gotchas](#14-patterns--gotchas)

---

## 0. Conventions & Auth

### 0.1 API versioning & URL shape

ELITEA exposes two coexisting API surfaces. **v2 is the canonical layer** and what every new integration should target; v1 remains for legacy consumers and a handful of subsystems that have not migrated yet.

| Subsystem | v2 prefix (preferred) | v1 prefix (legacy / only-form) |
|---|---|---|
| Agents, versions, predict, publish | `/api/v2/elitea_core/...` | `/api/v1/applications/...` |
| Conversations, messages, participants, attachments, folders, canvas | `/api/v2/elitea_core/...` | `/api/v1/chat/...` |
| Toolkits, MCP discovery, tool tests | `/api/v2/elitea_core/...` | `/api/v1/applications/...` |
| Collections, tags | `/api/v2/elitea_core/...` | `/api/v1/promptlib_shared/...` |
| **Configurations / Credentials** | — *(v1 only)* | `/api/v1/configurations/...` |
| **Artifacts / Buckets** | — *(v1 only)* | `/api/v1/artifacts/...` |
| **Secrets** | — *(v1 only)* | `/api/v1/secrets/...` |
| Notifications | `/api/v2/notifications/...` | — |

Most endpoints embed a `mode` segment between the resource and `{project_id}`:

```
/api/v2/elitea_core/<resource>/<mode>/<project_id>/...
```

`<mode>` values:
- `prompt_lib` — canonical UI/API mode; use this for ~95% of endpoints
- `default` — used by MCP proxies, secrets, artifacts, tools_list, tools_call
- `administration` — admin-only endpoints (e.g., `vectorstore`)

> **Doc-style note:** sections 1–5 (legacy doc) use `{projectId}` camelCase placeholders matching frontend mutation hook code. Sections 6–14 use `{project_id}` snake_case matching the Python source. Both are placeholders — the runtime treats them identically.

### 0.2 Authentication

Every authenticated request:

```
Authorization: Bearer <PAT_or_Session_Token>
Accept: */*
Content-Type: application/json   # only on POST/PUT/PATCH with a body
```

- Tokens are issued via the ELITEA Settings UI as Personal Access Tokens (PATs).
- No `X-API-Key`, no `User-Agent` is required.
- A small set of endpoints accept additional headers documented inline:
  - `X-SECRET` — required by `PATCH /version/...` for server-to-server expanded version details (returns unsecreted/resolved configuration values).
  - `X-USERSESSION` — used alongside `X-SECRET`; pass `-` for "current user".
  - `X-Toolkit-Tokens` — JSON-encoded OAuth tokens passed to `toolkit_validator` for MCP connection tests.
  - `X-Hub-Signature-256` / `X-Gitlab-Token` — webhook signature headers consumed by `POST /webhook/...`.

### 0.3 ID conventions — the `id` vs `uuid` split

This trips up integrators most often. Pay attention:

| Resource | Integer `id` used in… | UUID/string used in… |
|---|---|---|
| Conversation | participants endpoints, conversation update/delete, entity_settings, attachments | **`POST /messages/.../{conversation_uuid}`** (send message) |
| Message group | (rare) | **`GET /message/.../{uuid}`**, **`DELETE /message/.../{uuid}`**, **`POST /regenerate/.../{uuid}`** |
| Canvas | — | `GET/PUT /canvas/.../{canvas_uuid}` |
| Configuration | `PUT /configuration/{project_id}/{configuration_id}` | when referenced inside toolkit settings, use `{"elitea_title": "...", "private": <bool>}` instead of id |

> **Rule of thumb:** if you got the value from a `POST .../conversations` response and you're about to call `.../messages/`, use the `uuid` field. Everywhere else use `id`.

### 0.4 Secret placeholders

When you `GET` a configuration, credential, or toolkit settings, secret-typed fields come back as templated placeholders, **not** as `null` and **not** as the raw value:

```json
{ "data": { "access_token": "{{secret.gh_pat_abc123}}" } }
```

To resolve:
- `GET /api/v1/secrets/secret/default/{project_id}/{secret_name}` → `{"value": "ghp_..."}`
- OR call `PATCH /api/v2/elitea_core/version/prompt_lib/{project_id}/{application_id}/{version_id}` with the `X-SECRET` header — returns the version with all configuration references *resolved* inline.

The list of fields that get secret-vaulted (from `SENSITIVE_TOOLKIT_SETTINGS`):
`access_key, password, username, api_key, access_token, token, app_private_key, google_cse_id, google_api_key, app_id, client_secret, gitlab_personal_access_token, private_token, sonar_token, qtest_api_token, client_id, oauth2`.

### 0.5 Status code conventions

| Code | Meaning in this API |
|---|---|
| 200 | OK; also returned by **configuration create** (`POST /api/v1/configurations/...`) — unlike most other creates |
| 201 | Created (most POSTs) |
| 202 | Accepted — message still streaming, poll for completion |
| 204 | No Content — typical for DELETE, also for `is_private` rejection of public-project conversations |
| 207 | Multi-Status — used by `import_wizard` and `fork` when some sub-entities imported and others failed |
| 400 | Validation / business-rule failure — body usually `{"error": "..."}` or `{"detail": "..."}` |
| 403 | Project blocks publishing, or RBAC denied on a writable endpoint |
| 404 | Entity not found (or a "delete returned success=false" upstream condition) |
| 408 | MCP sync timeout (`mcp_sync_tools`) |
| 409 | Already published (publish endpoint) |
| 422 | Publish validation `FAIL` state |
| 500 | Internal error (publish, fork wrap) |

### 0.6 Base URL

- ELITEA (sole environment): `https://next.elitea.ai/`
- API root: prepend the base + `/api/v1/` or `/api/v2/` per the table in §0.1.

> The older `https://nexus.elitea.ai/` host has been retired. Treat any reference to it as outdated and update to `next.elitea.ai`.

---

## 1. Agents (Applications)

### 1.1 Create Agent

**Endpoint:** `POST /elitea_core/applications/prompt_lib/{projectId}`

**Frontend Implementation:**
- **Hook:** `useCreateApplication` (`AlitaUI/src/hooks/application/useCreateApplication.jsx`)
- **Mutation:** `useApplicationCreateMutation` (`AlitaUI/src/api/applications.js:862`)
- **Form:** `ApplicationCreateForm.jsx`

**Request Payload Structure:**

```json
{
  "name": "string (required)",
  "description": "string (required)",
  "type": "interface",
  "webhook_secret": "string | null (optional)",
  "versions": [
    {
      "name": "Latest",
      "tags": ["tag1", "tag2"],
      "instructions": "string",
      "variables": [
        {
          "name": "string",
          "value": "string"
        }
      ],
      "tools": [],
      "llm_settings": {
        "max_tokens": 4096,
        "temperature": 0.7,
        "reasoning_effort": "medium",
        "model_name": "string",
        "model_project_id": 0
      },
      "conversation_starters": ["string"],
      "agent_type": "openai",
      "welcome_message": "string",
      "meta": {
        "icon_meta": {},
        "step_limit": 25
      }
    }
  ]
}
```

**Dummy Example:**

```json
{
  "name": "Customer Support Assistant",
  "description": "An AI agent to help with customer inquiries and support tickets",
  "type": "interface",
  "webhook_secret": null,
  "versions": [
    {
      "name": "Latest",
      "tags": ["support", "customer-service", "helpdesk"],
      "instructions": "You are a helpful customer support assistant. Your role is to:\n1. Greet customers warmly\n2. Understand their issues\n3. Provide clear solutions\n4. Escalate complex issues when needed\n\nAlways be polite and professional.",
      "variables": [
        {
          "name": "customer_name",
          "value": ""
        },
        {
          "name": "ticket_id",
          "value": ""
        }
      ],
      "tools": [],
      "llm_settings": {
        "max_tokens": 2048,
        "temperature": 0.7,
        "reasoning_effort": "medium",
        "model_name": "claude-sonnet-4-5",
        "model_project_id": 123
      },
      "conversation_starters": [
        "I need help with my order",
        "How do I reset my password?",
        "I want to return a product",
        "When will my package arrive?"
      ],
      "agent_type": "openai",
      "welcome_message": "Hello! I'm your customer support assistant. How can I help you today?",
      "meta": {
        "icon_meta": {
          "icon": "support",
          "color": "#4A90E2"
        },
        "step_limit": 25
      }
    }
  ]
}
```

**Supporting APIs:**

| API | Endpoint | Purpose |
|-----|----------|---------|
| Get Models | `GET /configurations/models/{projectId}?include_shared=true` | Fetch available LLM models |
| Get Tags | `GET /elitea_core/tags/prompt_lib/{projectId}` | Fetch available tags |
| Get Icons | `GET /elitea_core/upload_icon/prompt_lib/{projectId}` | Fetch custom icons |
| Get Default Icons | `GET /elitea_core/default_icons/prompt_lib/{projectId}` | Fetch default icons |

---

### 1.2 Update Agent Entity

**Endpoint:** `PUT /elitea_core/application/prompt_lib/{projectId}/{applicationId}`

**Frontend Implementation:**
- **Hook:** `useSaveVersion` (`AlitaUI/src/hooks/application/useSaveVersion.js`)
- **Mutation:** `useApplicationEditMutation`

**Key Characteristics:**
- Updates entity metadata (name, description, owner, webhook)
- Updates default version details (nested in `version` object)
- Used when saving from main application editor

**Request Payload Structure:**

```json
{
  "name": "string",
  "description": "string",
  "id": 0,
  "projectId": 0,
  "owner_id": 0,
  "webhook_secret": "string | null",
  "version": {
    "name": "string",
    "tags": ["string"],
    "instructions": "string",
    "variables": [
      {
        "name": "string",
        "value": "string"
      }
    ],
    "tools": [],
    "llm_settings": {
      "max_tokens": 4096,
      "temperature": 0.7,
      "reasoning_effort": "medium",
      "model_name": "string",
      "model_project_id": 0
    },
    "conversation_starters": ["string"],
    "agent_type": "openai",
    "welcome_message": "string",
    "meta": {
      "icon_meta": {},
      "step_limit": 25
    }
  }
}
```

**Dummy Example:**

```json
{
  "name": "Customer Support Assistant v2",
  "description": "Enhanced AI agent with multilingual support for customer inquiries",
  "id": 456,
  "projectId": 123,
  "owner_id": 789,
  "webhook_secret": "<webhook-secret-placeholder>",
  "version": {
    "name": "v2.1",
    "tags": ["support", "customer-service", "multilingual"],
    "instructions": "You are a multilingual customer support assistant. Your role is to:\n1. Detect customer language\n2. Respond in their preferred language\n3. Understand their issues\n4. Provide clear solutions\n5. Escalate complex issues when needed\n\nSupported languages: English, Spanish, French, German",
    "variables": [
      {
        "name": "customer_name",
        "value": "John Doe"
      },
      {
        "name": "ticket_id",
        "value": "TKT-2024-001"
      },
      {
        "name": "preferred_language",
        "value": "en"
      }
    ],
    "tools": [
      {
        "toolkit_id": 101,
        "toolkit_name": "Translation Toolkit",
        "selected_tools": ["translate_text", "detect_language"]
      }
    ],
    "llm_settings": {
      "max_tokens": 3096,
      "temperature": 0.6,
      "reasoning_effort": "high",
      "model_name": "claude-opus-4-6",
      "model_project_id": 123
    },
    "conversation_starters": [
      "I need help with my order",
      "¿Cómo restablezco mi contraseña?",
      "Je veux retourner un produit",
      "Wann kommt mein Paket an?"
    ],
    "agent_type": "openai",
    "welcome_message": "Hello! I'm your multilingual support assistant. I can help you in English, Spanish, French, or German. How can I assist you today?",
    "meta": {
      "icon_meta": {
        "icon": "support_agent",
        "color": "#2ECC71"
      },
      "step_limit": 30
    }
  }
}
```

---

### 1.3 Update Agent Version

**Endpoint:** `PUT /elitea_core/version/prompt_lib/{projectId}/{applicationId}/{versionId}`

**Frontend Implementation:**
- **Hook:** `useSaveSpecificVersion` (`AlitaUI/src/hooks/application/useSaveSpecificVersion.js`)
- **Mutation:** `useUpdateApplicationVersionMutation`

**Key Characteristics:**
- Updates ONLY a specific version
- Flat payload structure (NO nested `version` object)
- Does NOT include entity-level fields (name, description, owner_id)
- Used when editing historical versions

**Request Payload Structure:**

```json
{
  "projectId": 0,
  "applicationId": 0,
  "versionId": 0,
  "name": "string",
  "tags": ["string"],
  "instructions": "string",
  "variables": [
    {
      "name": "string",
      "value": "string"
    }
  ],
  "tools": [],
  "llm_settings": {
    "max_tokens": 4096,
    "temperature": 0.7,
    "reasoning_effort": "medium",
    "model_name": "string",
    "model_project_id": 0
  },
  "conversation_starters": ["string"],
  "agent_type": "openai",
  "welcome_message": "string",
  "meta": {
    "icon_meta": {},
    "step_limit": 25
  }
}
```

**Dummy Example:**

```json
{
  "projectId": 123,
  "applicationId": 456,
  "versionId": 789,
  "name": "v2.0-stable",
  "tags": ["support", "customer-service", "production"],
  "instructions": "You are a customer support assistant specialized in technical troubleshooting.\n\nYour responsibilities:\n1. Diagnose technical issues\n2. Provide step-by-step solutions\n3. Document resolved cases\n4. Escalate unresolved issues\n\nAlways ask clarifying questions before providing solutions.",
  "variables": [
    {
      "name": "customer_id",
      "value": "CUST-12345"
    },
    {
      "name": "issue_category",
      "value": "technical"
    }
  ],
  "tools": [
    {
      "toolkit_id": 202,
      "toolkit_name": "Knowledge Base Search",
      "selected_tools": ["search_articles", "find_solutions"]
    }
  ],
  "llm_settings": {
    "max_tokens": 2048,
    "temperature": 0.5,
    "reasoning_effort": "medium",
    "model_name": "claude-sonnet-4-5",
    "model_project_id": 123
  },
  "conversation_starters": [
    "My device won't turn on",
    "I'm getting an error message",
    "How do I troubleshoot connectivity issues?",
    "The app keeps crashing"
  ],
  "agent_type": "openai",
  "welcome_message": "Hi! I'm here to help you troubleshoot technical issues. Please describe the problem you're experiencing.",
  "meta": {
    "icon_meta": {
      "icon": "engineering",
      "color": "#FF6B6B"
    },
    "step_limit": 20
  }
}
```

---

### 1.4 Create New Version

**Endpoint:** `POST /elitea_core/versions/prompt_lib/{projectId}/{applicationId}`

**Frontend Implementation:**
- **Mutation:** `useSaveApplicationNewVersionMutation`

**Request Payload:** Same as [Update Agent Version](#13-update-agent-version) (flat structure)

**Dummy Example:**

```json
{
  "projectId": 123,
  "applicationId": 456,
  "name": "v3.0-beta",
  "tags": ["support", "ai-enhanced", "beta"],
  "instructions": "You are an advanced AI customer support agent with proactive problem-solving capabilities.\n\nNew features in v3.0:\n- Sentiment analysis\n- Predictive issue detection\n- Automated ticket categorization\n- Smart routing to specialists\n\nProvide empathetic and efficient support.",
  "variables": [
    {
      "name": "customer_tier",
      "value": "premium"
    },
    {
      "name": "interaction_history",
      "value": "[]"
    }
  ],
  "tools": [
    {
      "toolkit_id": 303,
      "toolkit_name": "Sentiment Analysis",
      "selected_tools": ["analyze_sentiment", "detect_urgency"]
    },
    {
      "toolkit_id": 304,
      "toolkit_name": "CRM Integration",
      "selected_tools": ["fetch_customer_data", "update_ticket"]
    }
  ],
  "llm_settings": {
    "max_tokens": 4096,
    "temperature": 0.6,
    "reasoning_effort": "high",
    "model_name": "claude-opus-4-6",
    "model_project_id": 123
  },
  "conversation_starters": [
    "I have a problem with my account",
    "I need urgent assistance",
    "Can you check my order status?",
    "I want to upgrade my subscription"
  ],
  "agent_type": "openai",
  "welcome_message": "Welcome! I'm your enhanced support assistant with advanced capabilities. How may I help you today?",
  "meta": {
    "icon_meta": {
      "icon": "smart_toy",
      "color": "#9B59B6"
    },
    "step_limit": 35
  }
}
```

---

## 2. Pipelines

### 2.1 Create Pipeline

**Endpoint:** `POST /elitea_core/applications/prompt_lib/{projectId}` (same as agents)

**Frontend Implementation:**
- **Form:** `PipelineConfigurationForm.jsx`
- **Component:** `CreatePipeline.jsx`

**Key Differences from Agent:**
- `agent_type: "pipeline"` (instead of "openai")
- `instructions` contains YAML code
- Includes `pipeline_settings` object

**Request Payload Structure:**

```json
{
  "name": "string",
  "description": "string",
  "type": "interface",
  "webhook_secret": "string | null",
  "versions": [
    {
      "name": "Latest",
      "tags": ["string"],
      "instructions": "YAML code as string",
      "variables": [],
      "tools": [],
      "llm_settings": {
        "max_tokens": 4096,
        "temperature": 0.7,
        "reasoning_effort": "medium",
        "model_name": "string",
        "model_project_id": 0
      },
      "conversation_starters": ["string"],
      "agent_type": "pipeline",
      "welcome_message": "string",
      "pipeline_settings": {
        "nodes": [],
        "edges": [],
        "orientation": "vertical",
        "layout_version": 1
      },
      "meta": {
        "icon_meta": {},
        "step_limit": 25
      }
    }
  ]
}
```

**Dummy Example:**

```json
{
  "name": "Content Creation Pipeline",
  "description": "Multi-stage pipeline for generating, reviewing, and publishing content",
  "type": "interface",
  "webhook_secret": null,
  "versions": [
    {
      "name": "Latest",
      "tags": ["content", "automation", "publishing"],
      "instructions": "version: v1.0\nname: Content Creation Pipeline\n\nsteps:\n  - id: generate\n    name: Generate Content\n    agent: content_writer\n    input:\n      - topic\n      - keywords\n      - tone\n    output: draft_content\n    \n  - id: review\n    name: Review Content\n    agent: editor\n    input:\n      - draft_content\n    output: reviewed_content\n    conditions:\n      - quality_score > 0.8\n    \n  - id: seo_optimize\n    name: SEO Optimization\n    agent: seo_specialist\n    input:\n      - reviewed_content\n      - target_keywords\n    output: optimized_content\n    \n  - id: publish\n    name: Publish Content\n    action: publish_to_cms\n    input:\n      - optimized_content\n    output: published_url\n\nflow:\n  - from: generate\n    to: review\n  - from: review\n    to: seo_optimize\n    condition: approved\n  - from: seo_optimize\n    to: publish",
      "variables": [
        {
          "name": "topic",
          "value": ""
        },
        {
          "name": "keywords",
          "value": ""
        },
        {
          "name": "tone",
          "value": "professional"
        }
      ],
      "tools": [
        {
          "toolkit_id": 401,
          "toolkit_name": "Content Tools",
          "selected_tools": ["grammar_check", "plagiarism_check"]
        },
        {
          "toolkit_id": 402,
          "toolkit_name": "SEO Tools",
          "selected_tools": ["keyword_analysis", "readability_score"]
        }
      ],
      "llm_settings": {
        "max_tokens": 4096,
        "temperature": 0.7,
        "reasoning_effort": "medium",
        "model_name": "claude-sonnet-4-5",
        "model_project_id": 123
      },
      "conversation_starters": [
        "Create a blog post about AI trends",
        "Generate product description for new software",
        "Write a technical tutorial",
        "Create social media content series"
      ],
      "agent_type": "pipeline",
      "welcome_message": "Welcome to the Content Creation Pipeline! Provide your topic and requirements to get started.",
      "pipeline_settings": {
        "nodes": [
          {
            "id": "node-1",
            "type": "agent",
            "position": { "x": 100, "y": 100 },
            "data": {
              "label": "Content Writer",
              "agent_id": 501,
              "config": {}
            }
          },
          {
            "id": "node-2",
            "type": "agent",
            "position": { "x": 100, "y": 250 },
            "data": {
              "label": "Editor",
              "agent_id": 502,
              "config": {}
            }
          },
          {
            "id": "node-3",
            "type": "agent",
            "position": { "x": 100, "y": 400 },
            "data": {
              "label": "SEO Specialist",
              "agent_id": 503,
              "config": {}
            }
          },
          {
            "id": "node-4",
            "type": "action",
            "position": { "x": 100, "y": 550 },
            "data": {
              "label": "Publish",
              "action_type": "publish_to_cms"
            }
          }
        ],
        "edges": [
          {
            "id": "edge-1",
            "source": "node-1",
            "target": "node-2"
          },
          {
            "id": "edge-2",
            "source": "node-2",
            "target": "node-3"
          },
          {
            "id": "edge-3",
            "source": "node-3",
            "target": "node-4"
          }
        ],
        "orientation": "vertical",
        "layout_version": 1
      },
      "meta": {
        "icon_meta": {
          "icon": "account_tree",
          "color": "#3498DB"
        },
        "step_limit": 25
      }
    }
  ]
}
```

---

### 2.2 Update Pipeline

Pipelines use the **same update endpoints and payload structures as agents**:

1. **Update Pipeline Entity:** `PUT /elitea_core/application/prompt_lib/{projectId}/{applicationId}`
   - Same as [Update Agent Entity](#12-update-agent-entity)
   - Include `pipeline_settings` in nested `version` object

2. **Update Pipeline Version:** `PUT /elitea_core/version/prompt_lib/{projectId}/{applicationId}/{versionId}`
   - Same as [Update Agent Version](#13-update-agent-version)
   - Include `pipeline_settings` at root level

3. **Create New Pipeline Version:** `POST /elitea_core/versions/prompt_lib/{projectId}/{applicationId}`

**Dummy Example (Update Pipeline Entity):**

```json
{
  "name": "Advanced Content Pipeline v2",
  "description": "Enhanced pipeline with AI-powered content optimization and multi-channel distribution",
  "id": 678,
  "projectId": 123,
  "owner_id": 789,
  "webhook_secret": "<webhook-secret-placeholder>",
  "version": {
    "name": "v2.0",
    "tags": ["content", "automation", "multi-channel"],
    "instructions": "version: v2.0\nname: Advanced Content Pipeline\n\nsteps:\n  - id: ideation\n    name: Content Ideation\n    agent: idea_generator\n    input:\n      - industry\n      - target_audience\n    output: content_ideas\n    \n  - id: generate\n    name: Generate Content\n    agent: content_writer\n    input:\n      - selected_idea\n      - keywords\n      - tone\n    output: draft_content\n    \n  - id: enhance\n    name: AI Enhancement\n    agent: content_enhancer\n    input:\n      - draft_content\n    output: enhanced_content\n    \n  - id: review\n    name: Quality Review\n    agent: editor\n    input:\n      - enhanced_content\n    output: reviewed_content\n    \n  - id: optimize\n    name: Multi-Channel Optimization\n    parallel:\n      - id: seo\n        agent: seo_specialist\n        output: seo_version\n      - id: social\n        agent: social_media_optimizer\n        output: social_version\n      - id: email\n        agent: email_optimizer\n        output: email_version\n    \n  - id: publish\n    name: Multi-Channel Publishing\n    action: distribute_content\n    input:\n      - seo_version\n      - social_version\n      - email_version\n    output: distribution_report",
    "variables": [
      {
        "name": "industry",
        "value": "technology"
      },
      {
        "name": "target_audience",
        "value": "B2B professionals"
      },
      {
        "name": "content_type",
        "value": "blog"
      }
    ],
    "tools": [
      {
        "toolkit_id": 401,
        "toolkit_name": "Content Tools",
        "selected_tools": ["grammar_check", "plagiarism_check", "style_analyzer"]
      },
      {
        "toolkit_id": 402,
        "toolkit_name": "SEO Tools",
        "selected_tools": ["keyword_analysis", "readability_score", "meta_generator"]
      },
      {
        "toolkit_id": 403,
        "toolkit_name": "Social Media Tools",
        "selected_tools": ["hashtag_generator", "image_optimizer"]
      }
    ],
    "llm_settings": {
      "max_tokens": 5120,
      "temperature": 0.75,
      "reasoning_effort": "high",
      "model_name": "claude-opus-4-6",
      "model_project_id": 123
    },
    "conversation_starters": [
      "Generate thought leadership content",
      "Create a product launch campaign",
      "Build content for lead generation",
      "Develop educational content series"
    ],
    "agent_type": "pipeline",
    "welcome_message": "Welcome to the Advanced Content Pipeline! Let's create compelling content optimized for all your channels.",
    "pipeline_settings": {
      "nodes": [
        {
          "id": "node-ideation",
          "type": "agent",
          "position": { "x": 250, "y": 50 },
          "data": {
            "label": "Idea Generator",
            "agent_id": 601
          }
        },
        {
          "id": "node-writer",
          "type": "agent",
          "position": { "x": 250, "y": 180 },
          "data": {
            "label": "Content Writer",
            "agent_id": 602
          }
        },
        {
          "id": "node-enhancer",
          "type": "agent",
          "position": { "x": 250, "y": 310 },
          "data": {
            "label": "AI Enhancer",
            "agent_id": 603
          }
        },
        {
          "id": "node-editor",
          "type": "agent",
          "position": { "x": 250, "y": 440 },
          "data": {
            "label": "Editor",
            "agent_id": 604
          }
        },
        {
          "id": "node-seo",
          "type": "agent",
          "position": { "x": 100, "y": 600 },
          "data": {
            "label": "SEO Optimizer",
            "agent_id": 605
          }
        },
        {
          "id": "node-social",
          "type": "agent",
          "position": { "x": 250, "y": 600 },
          "data": {
            "label": "Social Media",
            "agent_id": 606
          }
        },
        {
          "id": "node-email",
          "type": "agent",
          "position": { "x": 400, "y": 600 },
          "data": {
            "label": "Email Optimizer",
            "agent_id": 607
          }
        },
        {
          "id": "node-publish",
          "type": "action",
          "position": { "x": 250, "y": 750 },
          "data": {
            "label": "Distribute",
            "action_type": "multi_channel_publish"
          }
        }
      ],
      "edges": [
        {
          "id": "e1",
          "source": "node-ideation",
          "target": "node-writer"
        },
        {
          "id": "e2",
          "source": "node-writer",
          "target": "node-enhancer"
        },
        {
          "id": "e3",
          "source": "node-enhancer",
          "target": "node-editor"
        },
        {
          "id": "e4",
          "source": "node-editor",
          "target": "node-seo"
        },
        {
          "id": "e5",
          "source": "node-editor",
          "target": "node-social"
        },
        {
          "id": "e6",
          "source": "node-editor",
          "target": "node-email"
        },
        {
          "id": "e7",
          "source": "node-seo",
          "target": "node-publish"
        },
        {
          "id": "e8",
          "source": "node-social",
          "target": "node-publish"
        },
        {
          "id": "e9",
          "source": "node-email",
          "target": "node-publish"
        }
      ],
      "orientation": "vertical",
      "layout_version": 2
    },
    "meta": {
      "icon_meta": {
        "icon": "hub",
        "color": "#E74C3C"
      },
      "step_limit": 40
    }
  }
}
```

---

## 3. Toolkits

### 3.1 Create Toolkit

**Endpoint:** `POST /elitea_core/tools/prompt_lib/{projectId}`

**Frontend Implementation:**
- **Hook:** `useCreateToolkit` (`AlitaUI/src/hooks/toolkit/useCreateToolkit.jsx`)
- **Mutation:** `useToolkitCreateMutation` (`AlitaUI/src/api/toolkits.js:503`)
- **Form:** `ToolkitForm.jsx`

**Request Payload Structure:**

```json
{
  "type": "string (required)",
  "name": "string (optional/required based on type)",
  "description": "string (optional/required based on type)",
  "settings": {
    "...": "type-specific configuration"
  },
  "meta": {}
}
```

**Dummy Examples by Toolkit Type:**

#### Example 1: API Toolkit

```json
{
  "type": "api",
  "name": "GitHub API Integration",
  "description": "Toolkit for interacting with GitHub REST API",
  "settings": {
    "base_url": "https://api.github.com",
    "authentication": {
      "type": "bearer",
      "token_key": "GITHUB_TOKEN"
    },
    "endpoints": [
      {
        "name": "list_repositories",
        "method": "GET",
        "path": "/user/repos",
        "description": "List all repositories for authenticated user",
        "parameters": {
          "per_page": 30,
          "sort": "updated"
        }
      },
      {
        "name": "create_issue",
        "method": "POST",
        "path": "/repos/{owner}/{repo}/issues",
        "description": "Create a new issue",
        "required_params": ["owner", "repo", "title"],
        "optional_params": ["body", "labels", "assignees"]
      }
    ],
    "headers": {
      "Accept": "application/vnd.github.v3+json",
      "User-Agent": "Elitea-Toolkit"
    },
    "timeout": 30
  },
  "meta": {
    "icon": "api",
    "category": "developer-tools"
  }
}
```

#### Example 2: Datasource Toolkit

```json
{
  "type": "datasource",
  "name": "Company Knowledge Base",
  "description": "Vector database for company documentation and internal knowledge",
  "settings": {
    "datasource_id": 12345,
    "embedding_model": {
      "model_name": "text-embedding-3-large",
      "model_project_id": 123
    },
    "vectorstore_model": {
      "model_name": "pinecone",
      "model_project_id": 123
    },
    "search_config": {
      "top_k": 5,
      "similarity_threshold": 0.7,
      "search_type": "similarity"
    },
    "metadata_filters": {
      "department": "engineering",
      "document_type": "technical_spec"
    }
  },
  "meta": {
    "icon": "storage",
    "last_indexed": "2026-02-13T10:30:00Z"
  }
}
```

#### Example 3: MCP (Model Context Protocol) Toolkit

```json
{
  "type": "mcp_server",
  "name": "Slack MCP Integration",
  "description": "MCP toolkit for Slack workspace operations",
  "settings": {
    "server_url": "https://mcp.slack.com/api",
    "authentication": {
      "type": "oauth",
      "client_id": "slack_client_id",
      "client_secret_key": "SLACK_CLIENT_SECRET"
    },
    "mcp_config": {
      "protocol_version": "1.0",
      "capabilities": [
        "channels.list",
        "messages.send",
        "users.list",
        "files.upload"
      ],
      "workspace_id": "T0123456789"
    },
    "timeout": 45,
    "ssl_verify": true,
    "auto_sync": true,
    "sync_interval": 3600
  },
  "meta": {
    "icon": "mcp",
    "last_synced": "2026-02-13T09:00:00Z"
  }
}
```

#### Example 4: Custom Python Toolkit

```json
{
  "type": "custom_python",
  "name": "Data Processing Toolkit",
  "description": "Custom Python tools for data transformation and analysis",
  "settings": {
    "python_version": "3.11",
    "dependencies": [
      "pandas>=2.0.0",
      "numpy>=1.24.0",
      "scikit-learn>=1.3.0"
    ],
    "tools": [
      {
        "name": "clean_dataset",
        "description": "Clean and preprocess dataset",
        "code": "def clean_dataset(data: pd.DataFrame) -> pd.DataFrame:\n    # Remove duplicates\n    data = data.drop_duplicates()\n    # Handle missing values\n    data = data.fillna(method='ffill')\n    # Remove outliers\n    return data",
        "input_schema": {
          "type": "object",
          "properties": {
            "data": {
              "type": "string",
              "description": "CSV data as string"
            }
          }
        },
        "output_schema": {
          "type": "string",
          "description": "Cleaned CSV data"
        }
      },
      {
        "name": "calculate_statistics",
        "description": "Calculate descriptive statistics",
        "code": "def calculate_statistics(data: pd.DataFrame, columns: list) -> dict:\n    stats = {}\n    for col in columns:\n        stats[col] = {\n            'mean': data[col].mean(),\n            'median': data[col].median(),\n            'std': data[col].std()\n        }\n    return stats"
      }
    ],
    "execution_timeout": 300,
    "memory_limit_mb": 512
  },
  "meta": {
    "icon": "code",
    "language": "python"
  }
}
```

**Supporting APIs:**

| API | Endpoint | Purpose |
|-----|----------|---------|
| Get Toolkit Types | `GET /elitea_core/toolkits/prompt_lib/{projectId}` | Fetch toolkit types with schemas |
| List Toolkit Types | `GET /elitea_core/toolkit_types/prompt_lib/{projectId}` | Get all available types |
| Discover MCP Tools | `POST /elitea_core/toolkit_discover_tools/prompt_lib/{projectId}/{toolkitType}` | Discover MCP server tools |
| Sync MCP Tools | `POST /elitea_core/mcp_sync_tools/prompt_lib/{projectId}` | Sync tools from MCP server |

---

### 3.2 Update Toolkit

**Endpoint:** `PUT /elitea_core/tool/prompt_lib/{projectId}/{toolId}`

**Frontend Implementation:**
- **Mutation:** `useToolkitEditMutation` (`AlitaUI/src/api/toolkits.js`)

**Request Payload Structure:**

```json
{
  "projectId": 0,
  "toolId": 0,
  "name": "string",
  "description": "string",
  "type": "string",
  "settings": {},
  "meta": {}
}
```

**Dummy Example:**

```json
{
  "projectId": 123,
  "toolId": 789,
  "name": "GitHub API Integration v2",
  "description": "Enhanced toolkit for GitHub REST and GraphQL APIs with advanced features",
  "type": "api",
  "settings": {
    "base_url": "https://api.github.com",
    "graphql_url": "https://api.github.com/graphql",
    "authentication": {
      "type": "bearer",
      "token_key": "GITHUB_TOKEN",
      "fallback_token_key": "GITHUB_BACKUP_TOKEN"
    },
    "endpoints": [
      {
        "name": "list_repositories",
        "method": "GET",
        "path": "/user/repos",
        "description": "List repositories with enhanced filtering",
        "parameters": {
          "per_page": 50,
          "sort": "updated",
          "visibility": "all",
          "affiliation": "owner,collaborator"
        },
        "cache_ttl": 300
      },
      {
        "name": "create_issue",
        "method": "POST",
        "path": "/repos/{owner}/{repo}/issues",
        "description": "Create issue with template support",
        "required_params": ["owner", "repo", "title"],
        "optional_params": ["body", "labels", "assignees", "milestone"],
        "validation": {
          "title_min_length": 5,
          "title_max_length": 200
        }
      },
      {
        "name": "search_code",
        "method": "GET",
        "path": "/search/code",
        "description": "Search code across repositories",
        "required_params": ["q"],
        "rate_limit_aware": true
      },
      {
        "name": "graphql_query",
        "method": "POST",
        "path": "/graphql",
        "description": "Execute GraphQL query",
        "is_graphql": true
      }
    ],
    "headers": {
      "Accept": "application/vnd.github.v3+json",
      "User-Agent": "Elitea-Toolkit-v2"
    },
    "timeout": 45,
    "retry_config": {
      "max_retries": 3,
      "backoff_factor": 2,
      "retry_on_status": [429, 500, 502, 503, 504]
    },
    "rate_limiting": {
      "enabled": true,
      "requests_per_hour": 5000
    }
  },
  "meta": {
    "icon": "api",
    "category": "developer-tools",
    "version": "2.0.0",
    "changelog": "Added GraphQL support, retry logic, and rate limiting"
  }
}
```

---

### 3.3 Associate/Disassociate Toolkit

**Endpoint:** `PATCH /elitea_core/tool/prompt_lib/{projectId}/{toolkitId}`

**Frontend Implementation:**
- **Mutation:** `useToolkitAssociateMutation` (`AlitaUI/src/api/toolkits.js`)

**Purpose:** Link or unlink a toolkit with an agent/pipeline

**Request Payload Structure:**

```json
{
  "projectId": 0,
  "toolkitId": 0,
  "entity_version_id": 0,
  "entity_id": 0,
  "entity_type": "agent | pipeline",
  "has_relation": true,
  "selected_tools": ["string"]
}
```

**Dummy Example (Associate):**

```json
{
  "projectId": 123,
  "toolkitId": 789,
  "entity_version_id": 456,
  "entity_id": 234,
  "entity_type": "agent",
  "has_relation": true,
  "selected_tools": [
    "list_repositories",
    "create_issue",
    "search_code"
  ]
}
```

**Dummy Example (Disassociate):**

```json
{
  "projectId": 123,
  "toolkitId": 789,
  "entity_version_id": 456,
  "entity_id": 234,
  "entity_type": "agent",
  "has_relation": false,
  "selected_tools": []
}
```

---

## 4. Credentials (Configurations)

### 4.1 Create Credential

**Endpoint:** `POST /configurations/configurations/{projectId}`

**Frontend Implementation:**
- **Hook:** `useCreateCredential` (`AlitaUI/src/hooks/credentials/useCreateCredential.jsx`)
- **Mutation:** `useCreateConfigurationMutation` (`AlitaUI/src/api/configurations.js`)

**Request Payload Structure:**

```json
{
  "projectId": 0,
  "body": {
    "alita_title": "string",
    "label": "string",
    "type": "string",
    "data": {},
    "shared": false
  }
}
```

**Dummy Examples by Credential Type:**

#### Example 1: OpenAI Credential

```json
{
  "projectId": 123,
  "body": {
    "alita_title": "OpenAI Production API",
    "label": "openai-prod",
    "type": "openai_api_key",
    "data": {
      "api_key": "<YOUR_OPENAI_API_KEY>",
      "organization_id": "org-XYZ123ABC456",
      "api_base": "https://api.openai.com/v1",
      "api_version": "2024-02-01"
    },
    "shared": false
  }
}
```

#### Example 2: AWS Credential

```json
{
  "projectId": 123,
  "body": {
    "alita_title": "AWS Production Account",
    "label": "aws-prod",
    "type": "aws_credentials",
    "data": {
      "aws_access_key_id": "<YOUR_AWS_ACCESS_KEY_ID>",
      "aws_secret_access_key": "<YOUR_AWS_SECRET_ACCESS_KEY>",
      "region": "us-east-1",
      "session_token": null
    },
    "shared": true
  }
}
```

#### Example 3: Database Credential

```json
{
  "projectId": 123,
  "body": {
    "alita_title": "Production PostgreSQL",
    "label": "postgres-prod",
    "type": "database_connection",
    "data": {
      "db_type": "postgresql",
      "host": "prod-db.example.com",
      "port": 5432,
      "database": "elitea_prod",
      "username": "elitea_user",
      "password": "SecureP@ssw0rd!2024",
      "ssl_mode": "require",
      "connection_timeout": 30,
      "pool_size": 10
    },
    "shared": false
  }
}
```

#### Example 4: OAuth Credential

```json
{
  "projectId": 123,
  "body": {
    "alita_title": "Google OAuth App",
    "label": "google-oauth",
    "type": "oauth2",
    "data": {
      "client_id": "123456789-abc123def456.apps.googleusercontent.com",
      "client_secret": "<YOUR_GOOGLE_OAUTH_CLIENT_SECRET>",
      "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
      "token_url": "https://oauth2.googleapis.com/token",
      "redirect_uri": "https://app.elitea.ai/oauth/callback",
      "scope": "openid email profile",
      "grant_type": "authorization_code"
    },
    "shared": false
  }
}
```

#### Example 5: API Key Credential (Generic)

```json
{
  "projectId": 123,
  "body": {
    "alita_title": "Stripe Production API",
    "label": "stripe-prod",
    "type": "api_key",
    "data": {
      "api_key": "<YOUR_STRIPE_API_KEY>",
      "api_base": "https://api.stripe.com/v1",
      "webhook_secret": "<your-webhook-secret-here>"
    },
    "shared": false
  }
}
```

---

### 4.2 Update Credential

**Endpoint:** `PUT /configurations/configuration/{projectId}/{configId}`

**Frontend Implementation:**
- **Hook:** `useUpdateCredential` (`AlitaUI/src/hooks/credentials/useUpdateCredential.jsx`)
- **Mutation:** `useUpdateConfigurationMutation` (`AlitaUI/src/api/configurations.js`)

**Request Payload Structure:**

```json
{
  "projectId": 0,
  "configId": 0,
  "body": {
    "alita_title": "string",
    "label": "string",
    "data": {},
    "meta": {},
    "shared": false
  }
}
```

**Dummy Example:**

```json
{
  "projectId": 123,
  "configId": 789,
  "body": {
    "alita_title": "OpenAI Production API v2",
    "label": "openai-prod-v2",
    "data": {
      "api_key": "<YOUR_OPENAI_API_KEY_ROTATED>",
      "organization_id": "org-XYZ123ABC456",
      "api_base": "https://api.openai.com/v1",
      "api_version": "2024-05-01",
      "default_model": "gpt-4-turbo",
      "max_retries": 3,
      "timeout": 60
    },
    "meta": {
      "last_rotated": "2026-02-13T10:00:00Z",
      "rotation_policy": "every_90_days",
      "usage_tracking": true,
      "cost_center": "engineering"
    },
    "shared": true
  }
}
```

---

## 5. Secrets

### 5.1 Create Secret

**Endpoint:** `POST /secrets/secrets/default/{projectId}`

**Frontend Implementation:**
- **Mutation:** `useSecretAddingMutation` (`AlitaUI/src/api/secrets.js`)

**Request Payload Structure:**

```json
{
  "name": "string",
  "value": "string",
  "description": "string (optional)"
}
```

**Dummy Examples:**

#### Example 1: API Key Secret

```json
{
  "name": "GITHUB_PAT",
  "value": "<YOUR_GITHUB_PAT>",
  "description": "GitHub Personal Access Token for repository operations"
}
```

#### Example 2: Database Password Secret

```json
{
  "name": "DB_PASSWORD",
  "value": "Sup3rS3cur3P@ssw0rd!2024",
  "description": "Production database password"
}
```

#### Example 3: Webhook Secret

```json
{
  "name": "SLACK_WEBHOOK_SECRET",
  "value": "T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX",
  "description": "Slack webhook URL for notifications"
}
```

#### Example 4: Encryption Key Secret

```json
{
  "name": "ENCRYPTION_KEY",
  "value": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6",
  "description": "AES-256 encryption key for sensitive data"
}
```

---

### 5.2 Update Secret

**Endpoint:** `PUT /secrets/secret/default/{projectId}/{name}`

**Frontend Implementation:**
- **Mutation:** `useSecretEditingMutation` (`AlitaUI/src/api/secrets.js`)

**Request Payload Structure:**

```json
{
  "projectId": 0,
  "name": "string",
  "value": "string",
  "description": "string (optional)"
}
```

**Dummy Example:**

```json
{
  "projectId": 123,
  "name": "GITHUB_PAT",
  "value": "<YOUR_GITHUB_PAT_ROTATED>",
  "description": "GitHub Personal Access Token for repository operations (rotated 2026-02-13)"
}
```

---

## 6. Conversations & Folders

A **conversation** is a stateful chat thread that binds together participants (users, agents, LLMs, toolkits, datasources), messages, attachments, and per-thread overrides. It is the primary runtime container for all ELITEA chat-based interaction.

> Source: `api/v2/conversations.py`, `api/v2/conversation.py`, `api/v2/select_conversation.py`, `api/v2/chat_config.py`, `api/v2/folder.py`.

### 6.1 List Conversations

**Endpoint:** `GET /api/v2/elitea_core/conversations/prompt_lib/{project_id}`
**Auth permission:** `models.chat.conversations.list`

**Query params:**

| Param | Type | Default | Notes |
|---|---|---|---|
| `query` | str | — | substring search on conversation name |
| `limit` | int | 10 | |
| `offset` | int | 0 | |
| `sort_by` | str | `created_at` | any `Conversation` column |
| `sort_order` | str | `desc` | `asc` / `desc` |
| `source` | str | `elitea` | also `support` for support-assistant project |
| `entity_meta_id` | int | — | filter by participant; alias `participant_id` |
| `entity_name` | str | — | filter by participant entity type |

**Response (200):**

```json
{
  "total": 50,
  "rows": [
    {
      "id": 300,
      "uuid": "a1b2c3d4-...",
      "name": "Support Chat #1",
      "is_private": true,
      "author_id": 5,
      "source": "alita",
      "participants_count": 2,
      "message_groups_count": 12,
      "users_count": 1,
      "duration": 1800.5,
      "created_at": "2026-01-15T10:30:00Z",
      "updated_at": "2026-01-15T11:00:00Z"
    }
  ]
}
```

### 6.2 Get Conversation Details

**Endpoint:** `GET /api/v2/elitea_core/conversation/prompt_lib/{project_id}/{conversation_id}`
**Auth permission:** `models.chat.conversation.details`

**Query params:**
| Param | Type | Default |
|---|---|---|
| `messages_limit` | int | 100 |
| `messages_offset` | int | 0 |
| `sort_order` | str | `acs` *(intentional typo in source; `desc` also accepted)* |

**Response (200):** Full `ConversationDetails` — see [§13 schema](#136-conversationdetails-shape).

### 6.3 Create Conversation

**Endpoint:** `POST /api/v2/elitea_core/conversations/prompt_lib/{project_id}`
**Auth permission:** `models.chat.conversations.create`

**Body (`ConversationCreate`):**

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `name` | str | yes | — | 3 ≤ len ≤ `CONVERSATION_NAME_MAX_LENGTH` |
| `is_private` | bool | no | `true` | Setting `false` in a *public* project → 400 |
| `participants` | list[ParticipantCreate] | no | `[]` | Extra participants; user + dummy auto-added |
| `source` | str | no | `elitea` | Lowercased, stripped |
| `meta` | dict | no | `{}` | User's persona / `default_instructions` auto-merged server-side |
| `instructions` | str | no | `""` | Filled from user's `default_instructions` if empty |
| `author_id` | int | — | — | Sent by client but **overwritten** with `current_user.id` |

**Minimal real-world payload (from `chat/conftest.py`):**

```json
{
  "author_id": 123,
  "is_private": true,
  "name": "Pytest: Test conversation",
  "participants": []
}
```

**Response (201):** Full `ConversationDetails` (id, uuid, participants, message_groups_count, meta with optional `context_strategy`, …).

> **Always capture both `id` and `uuid` from this response.** `id` is used everywhere except `POST .../messages/.../{conversation_uuid}` which requires the UUID. See [§0.3](#03-id-conventions--the-id-vs-uuid-split).

### 6.4 Update Conversation

**Endpoint:** `PUT /api/v2/elitea_core/conversation/prompt_lib/{project_id}/{conversation_id}`
**Auth permission:** `models.chat.conversation.update`

Patch-style — send only the fields you want to change.

**Body (any subset):**

| Field | Type | Notes |
|---|---|---|
| `name` | str | |
| `instructions` | str | |
| `is_private` | bool | |
| `is_hidden` | bool | |
| `meta` | dict | |
| `attachment_participant_id` | int | Pins the attachment toolkit participant |
| `folder_id` | int / null | Setting null moves out of folder |

**Example — move to folder, rename:**

```json
{ "folder_id": 42 }
```
```json
{ "name": "Updated conversation name", "is_private": true }
```

**Response (200):** Updated conversation. 400 with `{"error": ...}` on RPC failure.

### 6.5 Delete Conversation

**Endpoint:** `DELETE /api/v2/elitea_core/conversations/prompt_lib/{project_id}/{conversation_id}`
**Auth permission:** `models.chat.conversations.delete`
**Response:** 204 on success. 404 if upstream `success=false`.

### 6.6 Selected Conversation (UI state)

| Action | Method | Endpoint |
|---|---|---|
| Mark conversation as currently selected | `POST` | `/api/v2/elitea_core/select_conversation/prompt_lib/{project_id}/{conversation_id}` |
| Clear current selection | `DELETE` | `/api/v2/elitea_core/select_conversation/prompt_lib/{project_id}` |

Used by the web UI to remember which conversation is open across page loads; rarely needed by programmatic integrations.

### 6.7 Chat Config — attachment limits

**Endpoint:** `GET /api/v2/elitea_core/chat_config/prompt_lib/{project_id}`

**Response (200):** Vault-backed per-project limits:

```json
{
  "chat_max_upload_count": 10,
  "chat_max_upload_size_mb": 150,
  "chat_max_file_upload_size_mb": 150,
  "chat_max_image_upload_count": 10,
  "chat_max_image_upload_size_mb": 3
}
```

Call this **before** building an attachment-heavy UI to discover effective limits.

### 6.8 Folders

Folders organize conversations in the left sidebar.

| Action | Method | Endpoint | Notes |
|---|---|---|---|
| List | `GET` | `/api/v2/elitea_core/folder/prompt_lib/{project_id}` | Supports `grouped=true` (returns folders + first-page conversations), `date_group=today/this_week/older`, `folder_id={id}` |
| Create | `POST` | `/api/v2/elitea_core/folder/prompt_lib/{project_id}` | Body: `{"name": "...", "position?": int, "parent_id?": int, "meta?": dict}` |
| Update | `PUT` | `/api/v2/elitea_core/folder/prompt_lib/{project_id}/{folder_id}` | Body supports `neighbor_above_id` / `neighbor_below_id` for ordering rebalance |
| Pin/unpin | `PATCH` | `/api/v2/elitea_core/folder/prompt_lib/{project_id}/{folder_id}` | Body: `{"is_pinned": true}` |
| Delete | `DELETE` | `/api/v2/elitea_core/folder/prompt_lib/{project_id}/{folder_id}` | Conversations inside have `folder_id` set to null (NOT deleted) |

**Create example (from tests):**
```json
{ "name": "Pytest: Test conversation folder" }
```

---

## 7. Participants & Entity Settings

A **participant** is the binding of an entity (a user, an agent version, a toolkit, an LLM model, a datasource, or a placeholder "dummy") into a conversation, with optional per-conversation overrides.

> Source: `api/v2/participants.py`, `api/v2/participant.py`, `api/v2/entity_settings.py`.

### 7.1 Participant Types

| `entity_name` | `entity_meta` fields | Typical use |
|---|---|---|
| `user` | `{ "id": <user_id> }` | Add another human to a conversation |
| `llm` | `{ "model_name": "<model>" }` | Direct LLM chat (no agent) |
| `application` | `{ "id": <agent_id>, "project_id": <project_id>, "name?": "<label>" }` | Agent or pipeline |
| `toolkit` | `{ "id": <toolkit_id>, "project_id": <project_id> }` | Direct tool invocation |
| `datasource` | `{ "id": <datasource_id>, "project_id": <project_id> }` | RAG over a datasource |
| `dummy` | `{}` | Placeholder; auto-added by create-conversation |

### 7.2 Add Participants

**Endpoint:** `POST /api/v2/elitea_core/participants/prompt_lib/{project_id}/{conversation_id}`
**Auth permission:** `models.chat.participants.create`

> **Body must be a JSON LIST** even when adding one participant. Server returns a list.

**Add an agent (application) participant:**

```json
[
  {
    "entity_name": "application",
    "entity_meta": {
      "id": 17,
      "name": "Customer Support Agent",
      "project_id": 2
    },
    "entity_settings": {
      "variables": [],
      "icon_meta": {}
    }
  }
]
```

**Add an agent pinned to a specific version:**

```json
[
  {
    "entity_name": "application",
    "entity_meta": { "id": 17, "project_id": 2 },
    "entity_settings": { "variables": [], "icon_meta": {}, "version_id": 88 }
  }
]
```

**Add a toolkit participant** (for direct tool calls, no LLM loop):

```json
[
  {
    "entity_name": "toolkit",
    "entity_meta": { "id": 5, "name": "GitHub toolkit", "project_id": 2 },
    "entity_settings": {}
  }
]
```

**Add a published agent from another project** (e.g., from the public studio):

```json
[
  {
    "entity_name": "application",
    "entity_meta": { "id": 901, "project_id": 1 },
    "entity_settings": { "variables": [], "icon_meta": {}, "version_id": 902 }
  }
]
```

**Add a raw LLM participant:**

```json
[ { "entity_name": "llm", "entity_meta": { "model_name": "gpt-4o" } } ]
```

**Response:** `200` with `[<participant_details>]`. Extract `response[0].id` as the participant ID for subsequent `postEliteaCoreMessages` calls.

Server auto-fills missing `entity_meta.project_id` from the URL `project_id` (legacy compat).

### 7.3 Configure Participant — `entity_settings`

**Endpoint:**
- `PUT /api/v2/elitea_core/entity_settings/prompt_lib/{project_id}/{conversation_id}/{participant_id}` — full replacement
- `PATCH /api/v2/elitea_core/entity_settings/prompt_lib/{project_id}/{conversation_id}[/{participant_id}]` — partial; without `participant_id`, applies to the current user's participant

**Auth permission:** `models.chat.entity_settings.update`

**Body fields:**

| Field | Type | Applies to | Notes |
|---|---|---|---|
| `llm_settings` | `EntitySettingsLlm` | llm + application participants | model_name, temperature, max_tokens, reasoning_effort, model_project_id, chat_history_template |
| `version_id` (alias `id`) | int | application | Pin a specific agent version baseline |
| `variables` | list[`{name, value}`] | application | Per-conversation variable overrides |
| `chat_history_template` | `all` \| `interaction` \| `context_managed` \| int | application + llm | History strategy: all messages / current interaction only / auto-managed / last N |
| `icon_meta` | dict | application | UI metadata |

**`EntitySettingsLlm` shape:**
```json
{
  "model_name": "gpt-4o",
  "temperature": 0.5,
  "max_tokens": 8192,
  "reasoning_effort": "medium",
  "model_project_id": 2,
  "chat_history_template": "all"
}
```

**Version switch (always works):**
```json
{ "version_id": 88, "variables": [], "icon_meta": {} }
```

**Version switch + matching LLM settings:**
```json
{
  "version_id": 88,
  "variables": [],
  "llm_settings": {
    "max_tokens": 512,
    "top_p": 0.9,
    "temperature": 0.5,
    "model_project_id": 2,
    "model_name": "gpt-5"
  },
  "icon_meta": {}
}
```

**Per-conversation LLM override** (allowed ONLY against published public-project agents):
```json
{
  "variables": [],
  "icon_meta": {},
  "version_id": 902,
  "llm_settings": {
    "model_name": "gpt-5",
    "temperature": 0.9,
    "max_tokens": 128,
    "model_project_id": 1
  }
}
```

**Reset overrides** — PUT without the `llm_settings` key; cleared field becomes `null` or `{}` in the response.

**Response (200):** Updated participant with `entity_settings` populated. Emits SIO `chat_participant_update`.

**Critical gotcha — non-published agents:**
> For **non-published** application participants, an `llm_settings` override that differs from the version's baseline returns **400 `"LLM settings override is only allowed for published agents from agent studio"`**. For published agents (entity_meta.project_id == public_project_id) or non-application participants, the settings are validated and stored as-is.

**Whole-object replacement (PUT)**: fields not included in the new body are dropped. E.g., a previously-set `reasoning_effort: "high"` is removed by a subsequent PUT that omits it.

### 7.4 Remove Participant

**Endpoint:** `DELETE /api/v2/elitea_core/participant/prompt_lib/{project_id}/{conversation_id}/{participant_id}`
**Auth permission:** `models.chat.participant.delete`
**Response:** 204. 400 if participant not found or cannot be removed (e.g., the conversation author's own participant).

### 7.5 Get Participant (project-wide)

**Endpoint:** `GET /api/v2/elitea_core/participant/prompt_lib/{project_id}/{participant_id}`
**Response (200):** `ParticipantDetails`.

---

## 8. Messages, Attachments & Canvas

> Source: `api/v2/messages.py`, `api/v2/message.py`, `api/v2/regenerate.py`, `api/v2/attachments.py`, `api/v2/canvases.py`, `api/v2/canvas.py`.

### 8.1 List Messages

**Endpoint:** `GET /api/v2/elitea_core/messages/prompt_lib/{project_id}/{conversation_id}`
**Auth permission:** `models.chat.messages.list`

**Query params:**

| Param | Type | Default | Notes |
|---|---|---|---|
| `query` | str | — | ILIKE on `TextMessageItem.content` |
| `limit` | int | 10 | |
| `offset` | int | 0 | |
| `sort_by` | str | `created_at` | |
| `sort_order` | str | `desc` | |

**Response (200):**

```json
{
  "total": 24,
  "rows": [
    {
      "id": 500,
      "uuid": "msg-uuid-...",
      "author_participant_id": 1,
      "sent_to": { "id": 2, "participant_type": "application" },
      "reply_to_id": null,
      "is_streaming": false,
      "task_id": null,
      "created_at": "2026-01-15T10:31:00Z",
      "meta": {},
      "message_items": [
        {
          "id": 600,
          "uuid": "item-uuid-...",
          "order_index": 0,
          "item_type": "text_message",
          "item_details": { "content": "Hello, how can I help you?" },
          "meta": {}
        }
      ]
    }
  ]
}
```

### 8.2 Send Message — three shapes

**Endpoint:** `POST /api/v2/elitea_core/messages/prompt_lib/{project_id}/{conversation_uuid}`
**Auth permission:** `models.chat.messages.create`
**⚠️ Path uses `conversation_uuid` (string), NOT the integer `id`.**

**Body (`MessagePostPayload`):**

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `participant_id` | int | conditional* | None | Required for agent/toolkit-routed predict. None = direct LLM predict (then `llm_settings` must be provided) |
| `user_input` | str | conditional** | None | ** at least one of `user_input` / `tool_call_input` required |
| `tool_call_input` | `{tool_name, tool_params}` | conditional** | None | Direct tool invocation; bypasses the LLM loop |
| `await_task_timeout` | int | no | 30 | `-1`..`300` seconds; `-1` blocks forever; `0` fire-and-forget |
| `attachments_info` | list[`{filepath}`] | no | None | filepath in form `/{bucket}/{filename}` |
| `llm_settings` | dict | no | resolved | Required when `participant_id` is None |
| `return_task_id` | bool | no | false | **Mutex with `await_task_timeout > 0`** |

**Shape 1 — Send to an agent participant:**

```json
{
  "participant_id": 99,
  "user_input": "Summarize the latest sales report",
  "await_task_timeout": 30
}
```

**Shape 2 — Direct LLM (no agent):**

```json
{
  "user_input": "Return only one number from 0 to 10",
  "await_task_timeout": 30,
  "llm_settings": {
    "model_name": "gpt-5",
    "model_project_id": 2
  }
}
```

**Shape 3 — Direct toolkit invocation (no LLM loop):**

```json
{
  "participant_id": 101,
  "tool_call_input": {
    "tool_name": "get_files_from_directory",
    "tool_params": { "directory_path": "/" }
  },
  "await_task_timeout": 30
}
```

**Shape 4 — With attachments:**

```json
{
  "participant_id": 99,
  "user_input": "Analyze the attached document",
  "attachments_info": [{ "filepath": "/my-bucket/report.pdf" }],
  "await_task_timeout": 60
}
```

**Responses:**

- **201** — synchronous (reply completed within `await_task_timeout`):
  ```json
  {
    "message_groups": [
      { "id": 501, "uuid": "...", "author_participant_id": 1, "message_items": [{ "item_type": "text_message", "item_details": { "content": "..." } }] },
      { "id": 502, "uuid": "...", "author_participant_id": 99, "reply_to_id": 501, "meta": { "tool_calls": {...}, "thinking_steps": [...] }, "message_items": [...] }
    ]
  }
  ```
- **202** — still streaming after timeout. Same shape but assistant group has `is_streaming: true` and may have empty `message_items`. Poll with `GET /messages/...` or listen on SIO.
- **200** — when `return_task_id: true`:
  ```json
  { "task_id": "celery-task-id-string" }
  ```

**Response `meta` highlights:**
- `meta.tool_calls`: dict keyed by `run_id`; each entry `{ tool_name, tool_inputs, tool_output, error, finish_reason }`. `finish_reason: "stop"` indicates success. *(LLM-loop path only.)*
- `meta.thinking_steps[]`: each step has `generation_info.model_name` and/or `message.response_metadata.model_name` — useful to confirm which model actually executed.
- For toolkit-direct invocation (`tool_call_input`): NO `tool_calls`. Instead `meta.is_error: bool` and `meta.execution_time_seconds: float`. Server synthesizes `message_items[0].item_details.content` as `"Calling tool {tool_name}..."`.

**Validation notes:**
- `await_task_timeout < -1` → 400 `{"error"|"detail": ...}`
- Bad `conversation_uuid` or `participant_id` → 400 with `"...does not exist..."`

### 8.3 Get & Delete Single Message Group

| Action | Method | Endpoint |
|---|---|---|
| Get | `GET` | `/api/v2/elitea_core/message/prompt_lib/{project_id}/{message_group_uuid}` |
| Delete | `DELETE` | `/api/v2/elitea_core/message/prompt_lib/{project_id}/{message_group_uuid}` |

**Delete query params:**
- `delete_attachment` (any value): also removes attachment files from MinIO

**Delete restrictions (400 with):**
- `"Message can be deleted only by message or conversation author"`
- `"Summarized message can not be deleted"` (when `meta.context.included == false`)
- `"Only the last message in the conversation can be deleted"`

### 8.4 Delete All Messages

**Endpoint:** `DELETE /api/v2/elitea_core/messages/prompt_lib/{project_id}/{conversation_id}`
**Response:** 204. 400 if you are not the conversation author. Side effects: deletes LangGraph checkpoints, resets `context_analytics.meta`, emits `chat_message_delete_all` SIO event.

### 8.5 Regenerate Assistant Response

**Endpoint:** `POST /api/v2/elitea_core/regenerate/prompt_lib/{project_id}/{message_group_uuid}`
**Auth permission:** `models.chat.conversations.regenerate`

Re-runs the predict that produced this assistant message; replaces its `message_items` in place.

**Body (`SioRegenerateModel`):**
| Field | Type | Required |
|---|---|---|
| `payload` | dict | yes — inner predict payload (project_id, conversation_uuid, llm_settings, mcp_tokens, runtime_context, persona, …) |
| `sid` | str | yes — Socket.IO session id |
| `question_id` | str | yes |
| `conversation_uuid` | str | no |

**Response (200):** Refreshed `MessageGroupDetail`.

**Eligibility:**
- Only the conversation author OR the message-sender can regenerate.
- Only message groups whose `reply_to` participant is a `user` are regeneratable.

### 8.6 Attachments — Upload

**Endpoint:** `POST /api/v2/elitea_core/attachments/prompt_lib/{project_id}/{conversation_id}`
**Auth permission:** `models.chat.attachments.create`
**Content-Type:** `multipart/form-data`

**Single-shot upload:**

| Form field | Notes |
|---|---|
| `file` (repeatable) | binary file content; can include multiple `file` parts in one request |
| `overwrite_attachments` | `1` to overwrite same-named existing attachments; default `0` |

**Chunked upload** (large files):

| Form field | Notes |
|---|---|
| `file_id` | str — unique upload session ID |
| `chunk_index` | int — 0-based chunk index |
| `total_chunks` | int |
| `file_name` | str — original file name |
| `file` | binary — this chunk's bytes |
| `overwrite_attachments` | `0` or `1` |

**Response (200/201):**

```json
[
  { "filepath": "/bucket-name/uploaded-file.pdf", "file_size": 102400 }
]
```

After upload, reference the file in `postEliteaCoreMessages` via:

```json
"attachments_info": [{ "filepath": "/bucket-name/uploaded-file.pdf" }]
```

### 8.7 Attachments — Delete

**Endpoint:** `DELETE /api/v2/elitea_core/attachments/prompt_lib/{project_id}/{conversation_id}`

**Query params:**
- `filename` (repeatable): simple filename or `/{bucket}/{filename}` filepath
- `keep_in_storage`: `true|false|1|0` — when true, keeps MinIO object but unlinks DB record

**Response:** 204 on success; 400 with details of missing/failed files.

### 8.8 Canvas — Split a Text Message

A canvas is a code/document panel rendered inline inside a chat. Creating one splits the original `TextMessageItem` into `[pre_text, canvas, post_text]`.

**Endpoint:** `POST /api/v2/elitea_core/canvases/prompt_lib/{project_id}`

**Body (`CanvasItemCreatePayload`):**

| Field | Type | Required | Notes |
|---|---|---|---|
| `message_group_id` | int | yes | |
| `message_item_id` | int | yes | TextMessageItem id to split |
| `name` | str | yes | |
| `canvas_type` | enum `CanvasTypes` | yes | `code`, `document`, etc. |
| `meta` | dict | no | `{}` |
| `canvas_content_starts_at` | int | yes | char offset (≤ ends_at) |
| `canvas_content_ends_at` | int | yes | char offset |
| `code_language` | str | no | Auto-detected from ` ```lang ` fenced code blocks |

**Example:**
```json
{
  "message_group_id": 555,
  "message_item_id": 1234,
  "name": "Solution script",
  "canvas_type": "code",
  "meta": {},
  "canvas_content_starts_at": 0,
  "canvas_content_ends_at": 87,
  "code_language": "python"
}
```

**Response (200):** `CanvasItemDetail`. Emits SIO `chat_message_sync` on the conversation room. After creation, fetching the message shows `message_items: [text_message, canvas_message, text_message]`.

**Errors:** 400 if `canvas_content_ends_at < canvas_content_starts_at`.

### 8.9 Canvas — Get / Update

| Action | Method | Endpoint |
|---|---|---|
| Get | `GET` | `/api/v2/elitea_core/canvas/prompt_lib/{project_id}/{canvas_uuid}` |
| Update | `PUT` | `/api/v2/elitea_core/canvas/prompt_lib/{project_id}/{canvas_uuid}` |
| List in project | `GET` | `/api/v2/elitea_core/canvases/prompt_lib/{project_id}` |

**Update body:** `{ "name?": "...", "code_language?": "..." }`. Emits `chat_canvas_sync` to the canvas room.

### 8.10 Message Item Types — Reference

| `item_type` | `item_details` shape | Notes |
|---|---|---|
| `text_message` | `{ "content": "..." }` | Standard text |
| `canvas_message` | `{ "content": "...", "language": "python", "title": "..." }` | Code/document panel inline |
| `attachment_message` | `{ "filepath": "/bucket/file.pdf", "file_size": 1024 }` | File reference |

---

## 9. Tool & Toolkit Discovery (incl. MCP)

The "tools" surface is intentionally split:
- **Toolkit instance** — a configured integration (an API toolkit pointed at `github.com`, an MCP toolkit pointed at a specific MCP server, etc.).
- **Toolkit type** — the schema that defines what fields a toolkit instance needs. Used to drive the create form.
- **Tool** — an individual callable inside a toolkit (`create_issue`, `list_repos`, …). Discovered from the toolkit.

> Source: `api/v2/tools.py`, `api/v2/tool.py`, `api/v2/toolkits.py`, `api/v2/toolkit_types.py`, `api/v2/toolkit_available_tools.py`, `api/v2/toolkit_discover_tools.py`, `api/v2/toolkit_validator.py`, `api/v2/test_toolkit_tool.py`, `api/v2/mcp_sync_tools.py`, `api/v2/mcp_dcr_proxy.py`, `api/v2/mcp_oauth_proxy.py`.

### 9.1 List Toolkit Instances

**Endpoint:** `GET /api/v2/elitea_core/tools/prompt_lib/{project_id}`
**Auth permission:** `models.applications.tools.list`

**Query params:**

| Param | Type | Default | Notes |
|---|---|---|---|
| `query` | str | — | text search on toolkit names |
| `limit` / `offset` | int | 10 / 0 | |
| `sort_by` / `sort_order` | str | `created_at` / `desc` | |
| `toolkit_type` | str (repeatable) | — | Filter by one or more types |
| `mcp` | bool | false | Only MCP toolkits |
| `application` | bool | false | Only application-as-tool toolkits |
| `author_id` | int | — | |
| `search_artifact` | str | — | Search within artifact content |

**Response:**

```json
{
  "total": 15,
  "rows": [
    {
      "id": 55,
      "type": "github",
      "name": "My GitHub Toolkit",
      "description": "...",
      "author_id": 42,
      "settings": {...},
      "meta": {},
      "toolkit_name": "MyGitHubToolkit",
      "online": true,
      "icon_meta": null,
      "variables": [],
      "is_pinned": false,
      "created_at": "2026-01-01T00:00:00"
    }
  ]
}
```

### 9.2 Get Toolkit-Type Schemas

**Endpoint:** `GET /api/v2/elitea_core/toolkits/prompt_lib/{project_id}`
**Query:** `mcp=true|false` to filter to MCP-only types.

Returns the JSON-Schema registry of all toolkit *types* (e.g., `github`, `jira`, `mcp_filesystem`, `mcp_slack`, `custom_python`, `artifact`, `application`, `datasource`, …) — exactly what fields each type accepts in its `settings`.

This is the **registry the create-toolkit form is built from**. To discover what tools a `selected_tools` array can contain for a given type, drill into `<type>.properties.selected_tools.args_schemas` keys.

### 9.3 List Toolkit Types (names only)

**Endpoint:** `GET /api/v2/elitea_core/toolkit_types/prompt_lib/{project_id}`
**Query:** `mcp`, `application` boolean filters.
**Response:** `{ "rows": ["github", "jira", "mcp_slack", ...], "total": N }` — distinct types currently in use in this project.

### 9.4 List Available Tools in a Toolkit Instance

**Endpoint:** `GET /api/v2/elitea_core/toolkit_available_tools/prompt_lib/{project_id}/{toolkit_id}`
**Auth permission:** `models.applications.tool.details`

Dispatches a worker task to introspect the configured toolkit (live connection if MCP) and returns the tools it exposes. Use this after creating an MCP toolkit but before attaching tools to an agent — you'll need the tool names for `selected_tools`.

### 9.5 Discover MCP Tools (live, no toolkit yet)

**Endpoint:** `POST /api/v2/elitea_core/toolkit_discover_tools/prompt_lib/{project_id}/{toolkit_type}`

**Body:** `{ "settings": { ... } }` — or settings directly at the root. The "settings" payload is the same shape you'd pass to create the toolkit (server URL, auth, etc.).

**Purpose:** Live-connect to an MCP server and list its capabilities. Useful for validating a server URL before persisting a toolkit instance.

**Response:**
```json
{
  "success": true,
  "tools": [
    { "name": "search_files", "description": "...", "inputSchema": {...} }
  ],
  "args_schemas": { "search_files": { "type": "object", "properties": {...} } }
}
```

### 9.6 Sync Tools from MCP Server

**Endpoint:** `POST /api/v2/elitea_core/mcp_sync_tools/prompt_lib/{project_id}`
**Auth permission:** `models.applications.tool.patch`

**Body (`McpSyncToolsInputModel`):**

| Field | Notes |
|---|---|
| `url` | MCP server URL |
| `sid` | optional — Socket.IO session id for streaming progress |
| `toolkit_type` | optional — when prefixed `mcp_`, server merges in pylon config |
| `ssl_verify` | optional bool |

**Query:** `await_response=true|false` (default true), `timeout` (default 120 sync).

**Response:**
- **200** on success — returns the sync result
- **408** on timeout

### 9.7 Test a Tool — Live Invocation

**Endpoint:** `POST /api/v2/elitea_core/test_toolkit_tool/prompt_lib/{project_id}`
**Auth permission:** `models.applications.tool.patch`

**Body (`TestToolkitToolInputModel`):**
```json
{
  "project_id": 2,
  "toolkit_config": { /* full toolkit settings dict */ },
  "tool_name": "get_files_from_directory",
  "tool_params": { "directory_path": "/" },
  "llm_model": "gpt-5",
  "llm_settings": {
    "max_tokens": 1024,
    "temperature": 0.2,
    "top_p": 0.8,
    "model_name": "gpt-5"
  }
}
```

**Query:** `await_response=true|false` (default true), `timeout` (seconds; default 300 sync / -1 async).
**Response:** `task_id` (async) or full result (sync).

### 9.8 Validate Toolkit

**Endpoint:** `GET /api/v2/elitea_core/toolkit_validator/prompt_lib/{project_id}[/{toolkit_id}]`
**Auth permission:** `models.applications.toolkit_validator.check`
**Headers:** `X-Toolkit-Tokens: <json-encoded-oauth-tokens>` (for MCP servers requiring OAuth).

**Response:**
```json
{
  "error": false,
  "settings_errors": [],
  "connection_errors": []
}
```
200 on pass; 400 with the same shape + populated arrays on fail.

### 9.9 Link Agent to Toolkit (with tool selection)

**Endpoint:** `PATCH /api/v2/elitea_core/tool/prompt_lib/{project_id}/{tool_id}`

**Body:**
```json
{
  "entity_id": 7,
  "entity_version_id": 14,
  "entity_type": "agent",
  "has_relation": true,
  "selected_tools": ["create_issue", "list_issues"]
}
```

- `has_relation: true` to link, `false` to unlink.
- `selected_tools`: array of specific tool names to allow from this toolkit. If `null`, all tools are exposed.
- `entity_type`: `"agent"` (also accepts `"datasource"`).

**Response:** 201 on link; 200/201 on unlink.

### 9.10 MCP Dynamic Client Registration Proxy

**Endpoint:** `POST /api/v2/elitea_core/mcp_dcr_proxy/default/{project_id}`

**Body (`McpDynamicClientRegistrationRequest`, per RFC 7591):**
```json
{
  "registration_endpoint": "https://mcp.example.com/register",
  "redirect_uris": ["https://app.elitea.ai/oauth/callback"],
  "client_name": "ELITEA",
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "client_secret_basic",
  "application_type": "web",
  "scope": "read write",
  "software_id": "elitea",
  "software_version": "1.0"
}
```

### 9.11 MCP OAuth Token Proxy

**Endpoint:** `POST /api/v2/elitea_core/mcp_oauth_proxy/default/{project_id}`

**Body (`McpOAuthTokenRequest`):**
```json
{
  "token_endpoint": "https://mcp.example.com/oauth/token",
  "grant_type": "authorization_code",
  "code": "...",
  "redirect_uri": "https://app.elitea.ai/oauth/callback",
  "code_verifier": "...",
  "client_id": "...",
  "client_secret": "...",
  "scope": "read write",
  "toolkit_id": 55,
  "toolkit_type": "mcp_example"
}
```

> Masked secrets (`*****`) sent by the UI are detected and replaced server-side with the actual stored values from the DB.

---

## 10. Agent Execution (Predict)

There are TWO ways to actually run an agent against an input:

1. **Conversational** — `POST /messages/...` (covered in §8.2): full state, history, participants. Returns message groups.
2. **Stateless predict** — `POST /predict/...` or `POST /predict_llm/...` (this section): one-shot, no conversation persistence by default. Returns a raw result. Use for webhook handlers, JIRA bots, one-off RAG queries.

> Source: `api/v2/predict.py`, `api/v2/predict_llm.py`, `api/v2/application_task.py`.

### 10.1 Predict — Run an Agent Version

**Endpoint:** `POST /api/v2/elitea_core/predict/prompt_lib/{project_id}/{version_id}`
**Auth permission:** `models.applications.predict.post`

**Body — common fields:**

| Field | Type | Notes |
|---|---|---|
| `user_input` | str / list | The prompt / input |
| `chat_history` | list[`{role, content}`] | Optional prior turns; `role` ∈ `user`/`assistant` |
| `instructions` | str | Overrides version's `instructions` |
| `variables` | list[`{name, value}`] | Substitutes template variables |
| `llm_settings` | dict | Overrides `model_name`, `temperature`, `max_tokens`, `reasoning_effort`, `model_project_id` |
| `tools` | list | Overrides version's tool list |
| `thread_id` | str | LangGraph thread id (multi-turn without conversations) |
| `checkpoint_id` | str | Resume from a previous checkpoint |
| `conversation_id` | str | Conversation UUID for context (rare; predict is usually stateless) |
| `should_continue` | bool | Continue a previous execution |
| `meta` | dict | Free-form metadata; passed through to LangGraph |
| `callback_url` | str | If set → forces async; HTTP callback when done |
| `callback_headers` | dict | Sent with callback POST |

**Query:** `async=yes|true` also forces async mode.

**Synchronous example:**
```json
{
  "user_input": "What is the weather in Paris?",
  "llm_settings": { "temperature": 0.3, "max_tokens": 2048 },
  "variables": [{ "name": "language", "value": "English" }]
}
```

**Async with callback:**
```json
{
  "user_input": "Generate a full quarterly report",
  "async": "yes",
  "callback_url": "https://my-service.com/webhook/result",
  "callback_headers": { "Authorization": "Bearer token123" }
}
```

**Response — synchronous (200):**
```json
{ "result": "Agent response text...", "task_id": "celery-id", "error": null }
```

**Response — async (200):**
```json
{ "task_id": "celery-id", "result": null }
```

**Errors:** 400 with `{"error": "..."}` on `PredictPayloadError` / `ValidationError`.

### 10.2 Predict LLM — Raw Model Call

**Endpoint:** `POST /api/v2/elitea_core/predict_llm/prompt_lib/{project_id}`
**Auth permission:** `models.applications.predict.post`

Pure-LLM predict: no agent version, no tool loop, no LangGraph. Just direct model call.

**Body:**

| Field | Notes |
|---|---|
| `await_task_timeout` | int seconds, default 30; server pops this |
| `sid` | optional SIO session id for streaming |
| `model_name`, `model_project_id`, `temperature`, `max_tokens`, `top_p`, … | Standard LLM params |
| `messages` / `user_input` / `chat_history` | Input |

**Response:** `{ "result": "...", ... }`.

### 10.3 Application Task — Poll Result

When you got a `task_id` from a predict (async) or a `return_task_id`-style message:

**Get task status / result:**
- `GET /api/v2/elitea_core/application_task/prompt_lib/{project_id}/{task_id}`
- **Query:** `meta=yes|true`, `result=yes|true` — include extra fields.
- **Response:** `{ "status": "PENDING|STARTED|SUCCESS|FAILURE|REVOKED", "meta?": {...}, "result?": <agent output> }`

**Stop task:**
- The DELETE endpoint at `/application_task/.../{task_id}` is marked **DEPRECATED**. Use the platform's `task/{task_id}/stop` endpoint instead.

---

## 11. Lifecycle: Publish / Unpublish / Fork / Import-Export

> Source: `api/v2/publish.py`, `api/v2/publish_validate.py`, `api/v2/unpublish.py`, `api/v2/fork.py`, `api/v2/fork_toolkit.py`, `api/v2/export_toolkit.py`, `api/v2/export_import.py`, `api/v2/import_wizard.py`, `api/v2/default_version.py`, `api/v2/check_version_in_use.py`.

### 11.1 Validate Version for Publish

**Endpoint:** `POST /api/v2/elitea_core/publish_validate/prompt_lib/{project_id}/{version_id}`
**Auth permission:** `models.applications.publish.post`

**Body:**
```json
{ "version_name": "v1.0-schema" }
```

`version_name` must match `^[a-zA-Z0-9._-]{1,50}$` — letters, digits, dot, underscore, hyphen; 1–50 chars. Bad values are rejected with **400** at the Pydantic layer.

**Response (200 / 422):**
```json
{
  "status": "PASS",
  "critical_issues": [],
  "warnings": [],
  "recommendations": [],
  "summary": "...",
  "counts": { "critical": 0, "warnings": 0, "suggestions": 0 },
  "ai_validation_available": true,
  "validation_token": "PASS:123:hash:expiry"
}
```

- `status` ∈ `PASS`, `WARN`, `FAIL`. 422 returned when `FAIL`.
- `validation_token` is **non-null only when `status: "PASS"`** and can be passed to `/publish/...` to skip re-validation.

### 11.2 Publish Version

**Endpoint:** `POST /api/v2/elitea_core/publish/prompt_lib/{project_id}/{version_id}`
**Auth permission:** `models.applications.publish.post`

**Body:**
```json
{ "version_name": "pytest-v1", "validation_token": "PASS:123:..." }
```

`validation_token` is optional; if omitted, server runs inline validation. Same `version_name` regex applies.

**Two flows:**
- **Admin in-place** (when `project_id == public_project_id`) — toggles version status to `published` in-place.
- **User cross-project publish** — snapshots the source version, copies to public project, returns three IDs.

**Response (200/201):**
```json
{
  "public_agent_id": 902,
  "public_version_id": 903,
  "source_version_id": 905,
  "version_name": "pytest-v1"
}
```

| Field | Meaning |
|---|---|
| `public_agent_id` | New shell `Application` in the PUBLIC project |
| `public_version_id` | id of the published shell version inside the public project |
| `source_version_id` | **Clone** of the version created in the SOURCE project (status=`published`). Original draft is left untouched. |

**Limits:**
- `config.max_published_versions_per_agent` (default `3`).

**Errors:**
- **400** `publishing_blocked` — project blocks publishing AND user is not admin
- **404** `Version not found`
- **409** `already_published`
- **422** `validation_failed` (when inline validation fails)
- **500** `internal_error`

### 11.3 Unpublish Version

**Endpoint:** `POST /api/v2/elitea_core/unpublish/prompt_lib/{project_id}/{version_id}`
**Auth permission:** `models.applications.unpublish.post`

> **Important:** when un-publishing a cross-project published version, target the `source_version_id` (the clone in the source project), NOT the original draft.

**Body (optional):**
```json
{ "reason": "Deprecated by v2" }
```

**Response:** 200.

### 11.4 Fork an Agent or Pipeline

**Endpoint:** `POST /api/v2/elitea_core/fork/prompt_lib/{project_id}`
**Auth permission:** `models.applications.fork.post`

Forking wraps `import_wizard` but **sets `parent_entity_id`, `parent_project_id`, `parent_author_id`, `parent_version_id`** on each forked version's `meta`. This is what makes the new entity appear with `is_forked=true` in lists.

**Body shape** (Elitea export-bundle format):
```json
{
  "applications": [
    { "entity": "agents", "name": "Forked Agent", "versions": [{...}], ... }
  ],
  "toolkits": [
    { "entity": "toolkits", "name": "Forked Toolkit", ... }
  ]
}
```

**Responses:** 201 (all good), 207 (partial), 400 (all errored). Body: `{ "result": {...}, "errors": [...] }`.

**Note from tests:** the UI prepares fork payloads by overwriting `versions[0].llm_settings.{model_name, model_project_id}` with the target project's defaults (since the source project's model may not exist in the target).

### 11.5 Fork a Toolkit

**Endpoint:** `POST /api/v2/elitea_core/fork_toolkit/prompt_lib/{project_id}`

**Body (`ForkToolInput`):**
```json
{
  "toolkits": [
    { "id": 55, "owner_id": 42, "name": "...", "author_id": 42, "import_uuid": "...", ... }
  ]
}
```

Server checks for an existing fork via `find_existing_toolkit_fork` and sets parent metadata.

**Responses:** 201/207/200/400 + `{ "result": ..., "already_exists": [...], "errors": [...] }`.

### 11.6 Export Toolkits

**Endpoint:** `GET /api/v2/elitea_core/export_toolkit/prompt_lib/{project_id}/{toolkit_ids}`

`{toolkit_ids}` is a comma-separated string of integer IDs.

**Query:**
- `fork` (present) — mark as fork
- `as_file` (present) — download as `elitea_toolkits_{date}.json` attachment

**Response:** JSON export structure.

### 11.7 Export & Import Applications

| Action | Method | Endpoint |
|---|---|---|
| Export | `GET` | `/api/v2/elitea_core/export_import/prompt_lib/{project_id}/{application_id}` |
| Import (wizard) | `POST` | `/api/v2/elitea_core/import_wizard/prompt_lib/{project_id}/` |

**Export query:** `?fork=true` switches to fork-export shape (preserves UUIDs for re-import as fork).

**Export response:** `{ "applications": [...], "toolkits": [...] }`. Sensitive toolkit settings are stripped per [§0.4](#04-secret-placeholders).

**Import body — a plain LIST (not wrapped):**

```json
[
  {
    "entity": "agents",
    "name": "My Imported Agent",
    "description": "...",
    "versions": [
      {
        "name": "base",
        "tags": [],
        "instructions": "",
        "llm_settings": {
          "temperature": 0.7, "top_p": 0.8, "top_k": 20, "max_tokens": 512,
          "model_name": "gpt-5", "model_project_id": 2
        },
        "variables": [],
        "tools": [],
        "conversation_starters": [],
        "agent_type": "openai",
        "welcome_message": "",
        "created_at": "2024-08-28T08:08:50.053203",
        "import_version_uuid": "00000000-..."
      }
    ],
    "id": 1,
    "import_uuid": "00000000-...",
    "created_at": "2024-08-28T08:08:50.053203",
    "original_exported": true
  }
]
```

For agent→toolkit→agent linking, include both entries and reference the toolkit by `import_uuid` inside the agent's `tools[]`:

```json
[
  {
    "entity": "toolkits",
    "import_uuid": "a10000000-...",
    "name": "Agent-as-tool",
    "type": "application",
    "original_exported": true,
    "settings": {
      "variables": [],
      "import_uuid": "00000000-...",
      "import_version_uuid": "00000000-..."
    }
  },
  {
    "entity": "agents",
    "name": "Parent Agent",
    "versions": [{
      "...": "...",
      "tools": [{ "import_uuid": "a10000000-..." }]
    }]
  }
]
```

**Response:**
```json
{
  "result":  { "agents": [...], "toolkits": [...] },
  "errors":  { "agents": [{ "index": 2, "msg": "..." }], "toolkits": [...] }
}
```

**Status codes:**
- **201** — all imports clean
- **207** — partial success (some imports failed; check `errors`)
- **400** — hard validation failure (e.g., `agent_type: "INVALID_AGENT_TYPE"`)

### 11.8 Default Version & Version-In-Use

**Set default version:**
- `PATCH /api/v2/elitea_core/default_version/prompt_lib/{project_id}/{application_id}`
- Body: `{ "version_id": <int> }`
- Sets `application.meta.default_version_id`. Returns updated `ApplicationDetailModel`.

**Check if a version is in use** (before deleting):
- `GET /api/v2/elitea_core/check_version_in_use/prompt_lib/{project_id}/{application_id}/{version_id}`
- Returns referencing parents + safe replacement versions.

### 11.9 Application Relations (sub-agents / agent-as-tool)

**Endpoint:** `PATCH /api/v2/elitea_core/application_relation/prompt_lib/{project_id}/{application_id}[/{version_id}]`

> **URL/body convention is critical:** path holds the **CHILD** (the toolkit/sub-agent being attached). Body holds the **PARENT** (the agent that will host the sub-agent).

**Add a sub-agent:**
```json
{ "application_id": 7, "version_id": 14, "has_relation": true }
```

**Remove:**
```json
{ "application_id": 7, "version_id": 14, "has_relation": false }
```

**Errors:** 400 if `application_id == URL application_id` (self-binding blocked); 400 `"...already exist..."` on duplicate add.

### 11.10 Server-to-Server "Expanded" Version Details

When you need a version's tools with their credentials **resolved** (secrets decoded inline), use the PATCH variant:

**Endpoint:** `PATCH /api/v2/elitea_core/version/prompt_lib/{project_id}/{application_id}/{version_id}`

**Required headers:**
- `X-SECRET: <project_secret>`
- `X-USERSESSION: <session>` or `-` for current user

**Response:** version_details with credentials/configurations **expanded inline** — useful for executors that need the actual `access_token`, `password`, etc. without having to hit `/secrets/...` for each.

---

## 12. Pipeline Triggers & Webhooks

> Source: `api/v2/pipeline_trigger.py`, `api/v2/webhook.py`.

Pipelines can be invoked three ways:
1. `chat_message` — same as any agent (default).
2. `schedule` — periodic cron.
3. `webhook` — external HTTP trigger (GitHub events, GitLab events, custom).

### 12.1 Get Trigger Config

**Endpoint:** `GET /api/v2/elitea_core/{project_id}/pipeline/{version_id}/trigger`
**Auth permission:** `models.applications.version.details`

**Response:**
```json
{
  "type": "schedule",
  "cron": "0 9 * * MON-FRI",
  "timezone": "America/New_York",
  "last_run": "2026-05-24T13:00:00Z",
  "created_by": 42,
  "webhook_type": null,
  "webhook_url": null,
  "webhook_secret_masked": "**********"
}
```

> Secrets are **masked** for users without edit permission; users with edit permission see `webhook_secret_value` instead.

### 12.2 Set / Update Trigger Config

**Endpoint:** `PUT /api/v2/elitea_core/{project_id}/pipeline/{version_id}/trigger`
**Auth permission:** `models.applications.version.update`

**Body (`UpdatePipelineTrigger`):**

| Field | Required when | Notes |
|---|---|---|
| `type` | always | `chat_message` / `schedule` / `webhook` |
| `cron` | type=`schedule` | Standard cron expression |
| `timezone` | type=`schedule` | IANA timezone name |
| `webhook_type` | type=`webhook` | One of `github`, `gitlab`, `custom` |
| `webhook_secret_value` | optional | If omitted on `webhook`, server auto-generates |

**Examples:**
```json
{ "type": "schedule", "cron": "0 9 * * MON-FRI", "timezone": "America/New_York" }
```
```json
{ "type": "webhook", "webhook_type": "github" }
```

### 12.3 Rotate Webhook Secret

**Endpoint:** `POST /api/v2/elitea_core/{project_id}/pipeline/{version_id}/trigger`
**Purpose:** Regenerates the webhook secret. Only valid when `type=webhook`.

### 12.4 Webhook Entrypoint (incoming)

**Endpoint:** `POST /api/v2/elitea_core/webhook/prompt_lib/{project_id}/{version_id}/{webhook_type}`
**Auth:** **No bearer token** — secured by webhook signature.

| `webhook_type` | Signature header |
|---|---|
| `github` | `X-Hub-Signature-256: sha256=...` (HMAC-SHA256 of raw body with `webhook_secret_value`) |
| `gitlab` | `X-Gitlab-Token: <secret_value>` |
| `custom` | `X-Hub-Signature-256` (same as github) |

**Body:** raw provider payload — parsed and wrapped as `{"chat_history": [], "user_input": <raw>}` for legacy agents; native pipeline runs receive the payload as the `webhook` trigger context.

---

## 13. Quick Reference

### 13.1 API Endpoint Summary

**Entities — CRUD:**

| Entity | Create | Update Entity | Update Version |
|---|---|---|---|
| **Agent** | `POST /api/v2/elitea_core/applications/prompt_lib/{projectId}` | `PUT /api/v2/elitea_core/application/prompt_lib/{projectId}/{applicationId}` | `PUT /api/v2/elitea_core/version/prompt_lib/{projectId}/{applicationId}/{versionId}` |
| **Pipeline** | same as Agent (`agent_type: "pipeline"`) | same | same |
| **Toolkit** | `POST /api/v2/elitea_core/tools/prompt_lib/{projectId}` | `PUT /api/v2/elitea_core/tool/prompt_lib/{projectId}/{toolId}` | N/A |
| **Datasource** | `POST /datasources/datasources/prompt_lib/{projectId}` | `PUT /datasources/datasource/prompt_lib/{projectId}/{datasourceId}` | N/A |
| **Credential** | `POST /api/v1/configurations/configurations/{projectId}` *(returns 200)* | `PUT /api/v1/configurations/configuration/{projectId}/{configId}` | N/A |
| **Secret** | `POST /api/v1/secrets/secrets/default/{projectId}` | `PUT /api/v1/secrets/secret/default/{projectId}/{name}` | N/A |
| **Conversation** | `POST /api/v2/elitea_core/conversations/prompt_lib/{projectId}` | `PUT /api/v2/elitea_core/conversation/prompt_lib/{projectId}/{convId}` | N/A |
| **Folder** | `POST /api/v2/elitea_core/folder/prompt_lib/{projectId}` | `PUT/PATCH /api/v2/elitea_core/folder/prompt_lib/{projectId}/{folderId}` | N/A |
| **Collection** | `POST /api/v2/elitea_core/collections/prompt_lib/{projectId}` | `PUT /api/v2/elitea_core/collection/prompt_lib/{projectId}/{collectionId}` | N/A |
| **Bucket** | `POST /api/v1/artifacts/buckets/default/{projectId}` | N/A | N/A |
| **Artifact (file)** | `POST /api/v1/artifacts/artifacts/default/{projectId}/{bucket}` *(multipart)* | N/A | N/A |

**Runtime / chat:**

| Capability | Method | Endpoint |
|---|---|---|
| Add participants | `POST` | `/api/v2/elitea_core/participants/prompt_lib/{projectId}/{convId}` |
| Remove participant | `DELETE` | `/api/v2/elitea_core/participant/prompt_lib/{projectId}/{convId}/{participantId}` |
| Configure participant | `PUT`/`PATCH` | `/api/v2/elitea_core/entity_settings/prompt_lib/{projectId}/{convId}/{participantId}` |
| List messages | `GET` | `/api/v2/elitea_core/messages/prompt_lib/{projectId}/{convId}` |
| **Send message** | `POST` | `/api/v2/elitea_core/messages/prompt_lib/{projectId}/{convUUID}` |
| Get one message group | `GET` | `/api/v2/elitea_core/message/prompt_lib/{projectId}/{msgUUID}` |
| Delete one message group | `DELETE` | `/api/v2/elitea_core/message/prompt_lib/{projectId}/{msgUUID}` |
| Regenerate response | `POST` | `/api/v2/elitea_core/regenerate/prompt_lib/{projectId}/{msgUUID}` |
| Upload attachment | `POST` | `/api/v2/elitea_core/attachments/prompt_lib/{projectId}/{convId}` *(multipart)* |
| Create canvas | `POST` | `/api/v2/elitea_core/canvases/prompt_lib/{projectId}` |
| Chat-config (limits) | `GET` | `/api/v2/elitea_core/chat_config/prompt_lib/{projectId}` |

**Execution:**

| Capability | Method | Endpoint |
|---|---|---|
| Predict (run agent version) | `POST` | `/api/v2/elitea_core/predict/prompt_lib/{projectId}/{versionId}` |
| Direct LLM predict | `POST` | `/api/v2/elitea_core/predict_llm/prompt_lib/{projectId}` |
| Poll task status / result | `GET` | `/api/v2/elitea_core/application_task/prompt_lib/{projectId}/{taskId}` |

**Discovery (tools / toolkits / MCP):**

| Capability | Method | Endpoint |
|---|---|---|
| List toolkit instances | `GET` | `/api/v2/elitea_core/tools/prompt_lib/{projectId}` |
| Toolkit-type schemas | `GET` | `/api/v2/elitea_core/toolkits/prompt_lib/{projectId}` |
| List toolkit type names | `GET` | `/api/v2/elitea_core/toolkit_types/prompt_lib/{projectId}` |
| Available tools in a toolkit | `GET` | `/api/v2/elitea_core/toolkit_available_tools/prompt_lib/{projectId}/{toolkitId}` |
| Discover MCP server tools | `POST` | `/api/v2/elitea_core/toolkit_discover_tools/prompt_lib/{projectId}/{toolkitType}` |
| Sync MCP tools | `POST` | `/api/v2/elitea_core/mcp_sync_tools/prompt_lib/{projectId}` |
| Test a tool (live) | `POST` | `/api/v2/elitea_core/test_toolkit_tool/prompt_lib/{projectId}` |
| Link agent → toolkit | `PATCH` | `/api/v2/elitea_core/tool/prompt_lib/{projectId}/{toolkitId}` |

**Lifecycle:**

| Capability | Method | Endpoint |
|---|---|---|
| Validate version for publish | `POST` | `/api/v2/elitea_core/publish_validate/prompt_lib/{projectId}/{versionId}` |
| Publish version | `POST` | `/api/v2/elitea_core/publish/prompt_lib/{projectId}/{versionId}` |
| Unpublish version | `POST` | `/api/v2/elitea_core/unpublish/prompt_lib/{projectId}/{versionId}` |
| Fork agent | `POST` | `/api/v2/elitea_core/fork/prompt_lib/{projectId}` |
| Fork toolkit | `POST` | `/api/v2/elitea_core/fork_toolkit/prompt_lib/{projectId}` |
| Export application | `GET` | `/api/v2/elitea_core/export_import/prompt_lib/{projectId}/{applicationId}` |
| Export toolkits | `GET` | `/api/v2/elitea_core/export_toolkit/prompt_lib/{projectId}/{toolkitIds}` |
| Import wizard | `POST` | `/api/v2/elitea_core/import_wizard/prompt_lib/{projectId}/` |
| Set default version | `PATCH` | `/api/v2/elitea_core/default_version/prompt_lib/{projectId}/{applicationId}` |
| Check version-in-use | `GET` | `/api/v2/elitea_core/check_version_in_use/prompt_lib/{projectId}/{applicationId}/{versionId}` |

**Pipeline triggers / webhooks:**

| Capability | Method | Endpoint |
|---|---|---|
| Get trigger config | `GET` | `/api/v2/elitea_core/{projectId}/pipeline/{versionId}/trigger` |
| Set trigger config | `PUT` | `/api/v2/elitea_core/{projectId}/pipeline/{versionId}/trigger` |
| Rotate webhook secret | `POST` | `/api/v2/elitea_core/{projectId}/pipeline/{versionId}/trigger` |
| Incoming webhook (provider posts) | `POST` | `/api/v2/elitea_core/webhook/prompt_lib/{projectId}/{versionId}/{webhookType}` |

---

### 13.2 Key Differences: Entity Update vs Version Update

| Aspect | Entity Update | Version Update |
|--------|---------------|----------------|
| **Endpoint Pattern** | `/application/.../` | `/version/.../` |
| **Payload Structure** | Nested `version` object | Flat structure |
| **Updates** | Entity metadata + default version | Specific version only |
| **Includes** | name, description, owner_id, webhook_secret | Only version-specific fields |
| **Use Case** | Main editor save | Historical version edit |
| **Applies To** | Agents & Pipelines | Agents & Pipelines |

---

### 13.3 Entity Version Management

| Entity | Has Versions? | Version Structure | Update Pattern |
|--------|---------------|-------------------|----------------|
| **Agent** | ✅ Yes | Multiple versions with history | Separate entity & version updates |
| **Pipeline** | ✅ Yes | Multiple versions with history | Separate entity & version updates |
| **Toolkit** | ❌ No | Direct entity | Single update endpoint |
| **Datasource** | ⚠️ Simplified | `version_details` object | Single update (entire entity) |
| **Credential** | ❌ No | Direct entity | Single update endpoint |
| **Secret** | ❌ No | Direct value | Single update endpoint |

---

### 13.4 Key Discriminators

| Entity Type | Key Field | Value |
|-------------|-----------|-------|
| **Agent** | `agent_type` | `"openai"` |
| **Pipeline** | `agent_type` | `"pipeline"` |
| **Pipeline** | `pipeline_settings` | Object with nodes/edges |
| **Toolkit** | `type` | Toolkit type string (e.g., "api", "mcp_*") |

---

### 13.5 Common Supporting APIs

```
# Get available models for LLM configuration
GET /api/v1/configurations/models/{projectId}?include_shared=true

# Get models for specific sections (embedding, vectorstore, etc.)
GET /api/v1/configurations/models/{projectId}?section={section_type}

# Get tags for categorization
GET /api/v2/elitea_core/tags/prompt_lib/{projectId}

# Icon management
GET /api/v1/applications/upload_icon/prompt_lib/{projectId}
GET /api/v1/applications/default_icons/prompt_lib/{projectId}
POST /api/v1/applications/upload_icon/prompt_lib/{projectId}/{versionId}
PUT /api/v1/applications/upload_icon/prompt_lib/{projectId}/{versionId}
DELETE /api/v1/applications/upload_icon/prompt_lib/{projectId}/{name}

# Validation
GET /api/v2/elitea_core/version_validator/prompt_lib/{projectId}/{applicationId}/{versionId}
GET /api/v2/elitea_core/toolkit_validator/prompt_lib/{projectId}/{toolkitId}

# Toolkit discovery (MCP)
POST /api/v2/elitea_core/toolkit_discover_tools/prompt_lib/{projectId}/{toolkitType}
POST /api/v2/elitea_core/mcp_sync_tools/prompt_lib/{projectId}

# Secrets resolution
GET /api/v1/secrets/secret/default/{projectId}/{secret_name}

# Notifications
GET /api/v2/notifications/notifications/prompt_lib/{projectId}?only_new=true
```

### 13.6 ConversationDetails shape

Used by `GET /conversation/...`, returned by `POST /conversations/...`.

```json
{
  "id": 300,
  "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "name": "Support Chat #1",
  "is_private": true,
  "author_id": 5,
  "source": "alita",
  "attachment_participant_id": null,
  "instructions": "",
  "meta": { "context_strategy": {...}, "persona": "generic" },
  "created_at": "2026-01-15T10:30:00Z",
  "updated_at": "2026-01-15T11:00:00Z",
  "participants": [
    {
      "id": 1,
      "entity_name": "user",
      "entity_meta": { "id": 42 },
      "entity_settings": {},
      "meta": {}
    },
    {
      "id": 15,
      "entity_name": "application",
      "entity_meta": { "id": 101, "project_id": 2 },
      "entity_settings": {
        "version_id": 200,
        "variables": [{ "name": "tone", "value": "formal" }],
        "icon_meta": {},
        "llm_settings": null
      }
    }
  ],
  "message_groups_count": 12,
  "message_groups": []
}
```

### 13.7 End-to-end workflows

**Workflow A — Build & run a customer-support agent:**

1. `POST /api/v1/configurations/configurations/{project_id}` — create credential (e.g., OpenAI API key)
2. `POST /api/v2/elitea_core/tools/prompt_lib/{project_id}` — create toolkit (e.g., GitHub) referencing the credential
3. `POST /api/v2/elitea_core/applications/prompt_lib/{project_id}` — create agent with `versions: [{name: "base", llm_settings, ...}]`
4. `PATCH /api/v2/elitea_core/tool/prompt_lib/{project_id}/{tool_id}` — link toolkit to agent version with `selected_tools`
5. `POST /api/v2/elitea_core/conversations/prompt_lib/{project_id}` — create conversation
6. `POST /api/v2/elitea_core/participants/prompt_lib/{project_id}/{conv_id}` — add agent as participant; save `participant_id`
7. `POST /api/v2/elitea_core/messages/prompt_lib/{project_id}/{conv_uuid}` — send user message; receive assistant reply

**Workflow B — Stateless agent invocation (webhook/JIRA bot):**

1. `GET /api/v2/elitea_core/application/prompt_lib/{project_id}/{application_id}` — get `version_details.id`
2. `POST /api/v2/elitea_core/predict/prompt_lib/{project_id}/{version_id}` — fire-and-forget with `callback_url`
3. Receive callback POST at `callback_url`

**Workflow C — Publish for cross-project sharing:**

1. `POST /publish_validate/.../{version_id}` — capture `validation_token`
2. `POST /publish/.../{version_id}` with `version_name` + token
3. Distribute the `public_agent_id` to consumers
4. (Later) `POST /unpublish/.../{source_version_id}` — note: NOT the original draft id

**Workflow D — Add an MCP server as a toolkit:**

1. `POST /toolkit_discover_tools/prompt_lib/{project_id}/{toolkit_type}` — validate connection
2. `POST /tools/prompt_lib/{project_id}` — create the toolkit instance (type prefix `mcp_`)
3. `POST /mcp_sync_tools/prompt_lib/{project_id}` — sync tool definitions
4. `GET /toolkit_available_tools/prompt_lib/{project_id}/{toolkit_id}` — list tool names
5. `PATCH /tool/prompt_lib/{project_id}/{tool_id}` — link to agent with `selected_tools`

**Workflow E — Pipeline triggered by GitHub PR events:**

1. `POST /api/v2/elitea_core/applications/prompt_lib/{project_id}` with `agent_type: "pipeline"`, YAML in `instructions`
2. `PUT /api/v2/elitea_core/{project_id}/pipeline/{version_id}/trigger` body `{type: "webhook", webhook_type: "github"}`
3. `GET /trigger` → capture `webhook_url` and `webhook_secret_value`
4. Add a GitHub webhook pointing at `webhook_url` with the captured secret
5. GitHub events fire `POST /webhook/prompt_lib/{project_id}/{version_id}/github` automatically

---

## 14. Patterns & Gotchas

Distilled from the ELITEA `api/v2` source and the `elitea-api-testing` pytest suite. Each item is a real surprise an integrator can hit.

### 14.1 ID & UUID confusion

1. **`POST /messages/...` uses `conversation_uuid`** (string), not `conversation_id`. Every other conversation endpoint uses the integer `id`.
2. **`/message/{uuid}`** (singular) takes the message group UUID. **`/messages/...`** (plural) takes the conversation id.
3. **Canvas endpoints** all use `canvas_uuid`.

### 14.2 Body wrapping

4. **`POST /participants/...` body is a JSON LIST**, even for one participant. Response is also a list — always `response[0]`.
5. **`POST /import_wizard/...` body is a JSON LIST**, not `{items: [...]}`.
6. **`PUT /application/...`** uses singular `version` (object), **`POST /applications/...`** uses plural `versions` (array of exactly 1).

### 14.3 Permissions & ownership

7. **Only the conversation `author_id` may delete-all messages.** Other participants get 400 even with delete permission.
8. **A message group can only be deleted by the message author OR the conversation author**, AND only if it's the last message AND not summarized (`meta.context.included == false`).
9. **LLM-settings override is blocked for non-published agents.** Setting `entity_settings.llm_settings` to something different from the version's baseline returns 400 unless the agent is in the public project.
10. **The conversation author is auto-set server-side** — `author_id` you send in the body is overwritten with `current_user.id`.

### 14.4 Version & publishing rules

11. **First version of an agent MUST be named `"base"`**. Subsequent versions MUST NOT be `"base"`.
12. **Only ONE version is allowed at `POST /applications/...` time.** Use `POST /versions/...` to add more.
13. **`version_name` for publish must match `^[a-zA-Z0-9._-]{1,50}$`.** Spaces, special chars → 400.
14. **Publishing creates a CLONE** in the source project (status=published) and a SHELL in the public project. The original draft is left untouched. To unpublish, target `source_version_id` (the clone), not the draft.
15. **Default cap is 3 published versions per agent** (`config.max_published_versions_per_agent`).

### 14.5 Message / predict mechanics

16. **`await_task_timeout`** valid range is `-1..300` seconds. `-1` blocks forever; `0` fire-and-forget. Values below `-1` → 400.
17. **`return_task_id: true` is mutually exclusive with `await_task_timeout > 0`** — pick one mode.
18. **Toolkit-direct invocation (`tool_call_input`)** skips the LLM loop entirely. Response `meta` has `is_error` + `execution_time_seconds`, NOT `tool_calls`.
19. **Direct LLM predict requires `llm_settings`** when `participant_id` is null — otherwise 400.
20. **Step limit defaults to 25** if `meta.step_limit` is not set on the version. Bump it for long agentic chains.

### 14.6 Configuration & toolkit references

21. **`section` on configurations is server-assigned**, NOT client-sent. Don't include it in create payloads.
22. **`POST /configurations/...` returns 200**, not 201 — one of the few endpoints that breaks the convention.
23. **Toolkit settings reference credentials by `elitea_title`**, NEVER by raw id. Form is `{"elitea_title": "...", "private": true|false}`. `private = not credential.shared`.
24. **`toolkit_name` is the sanitized form of `name`.** Server strips `[^a-zA-Z0-9_.-]` and replaces `.` with `_` (see `utils/utils.py:15`).
25. **Sensitive credential fields** (`access_token`, `password`, `api_key`, etc.) come back as `"{{secret.<name>}}"` placeholders. Resolve via `GET /api/v1/secrets/secret/default/{project_id}/{secret_name}` or use the `X-SECRET` PATCH on `/version/...`.
26. **Configuration status polling** — AI/Embedding configurations need 1–5 s to validate. Poll `GET /configuration/{id}` until `status_ok: true` (test helper polls 5 times, 3 s apart).
27. **Buckets** — set `expiration_value: 30, expiration_measure: "days"` on bucket create to avoid a backend crash for projects with non-null `data_retention_limit`.

### 14.7 URL-segment surprises

28. **`mode` varies per subsystem**:
    - `prompt_lib/{project_id}` — most endpoints
    - `default/{project_id}` — secrets, artifacts, MCP proxies
    - `administration` — admin-only (no project context: `public_applications/prompt_lib`, `admin_published_agents/administration`)
29. **`application_relation` URL convention** — path holds the CHILD (sub-agent / toolkit), body holds the PARENT. Easy to invert.
30. **Singular vs plural**:
    - `tools/prompt_lib/{project_id}` (POST: create toolkit) — plural even though resource is a toolkit
    - `tool/prompt_lib/{project_id}/{toolkit_id}` (GET/DELETE) — singular
    - `participants/...` plural (POST add), `participant/...` singular (DELETE/GET)
    - Same pattern for `applications` / `application`, `versions` / `version`, `conversations` / `conversation`, `messages` / `message`
31. **Collection add-entity payload uses singular key `application`** (not `applications`) even for pipelines.
32. **Add-tool-to-entity body uses `entity_type: "agent"`** (singular), not `"applications"`.

### 14.8 Subtle response shapes

33. **`POST /publish/...` returns three IDs** — capture all of `public_agent_id`, `public_version_id`, `source_version_id`. The unpublish target is `source_version_id`.
34. **`messages.is_streaming: true`** on an assistant group with empty `message_items` means: poll or subscribe to SIO `chat_message_sync`.
35. **`message_groups[].meta.thinking_steps[i].generation_info.model_name`** reveals which model actually ran (after any `llm_settings` overrides).
36. **`import_wizard` returns 207** for partial success — check `errors.agents` and `errors.toolkits` even on 2xx responses.
37. **`fork` returns 207** for partial success similarly.

### 14.9 Defaults that bite

| Default | Where | Why it matters |
|---|---|---|
| `mode = "prompt_lib"` | most endpoints | Almost never need to change |
| `source = "elitea"` (lowercased) | conversation create | Server lowercases; mixed-case fails sorting |
| `step_limit = 25` | version `meta` | Long agentic loops need a bump |
| `await_task_timeout = 30` | message helpers | Long-running agents need `-1` |
| `messages_limit = 100` | GET conversation | Pagination needed for deep history |
| `is_private = true` | conversation create | False rejected in public project |
| `version name = "base"` | first version create | Hard requirement |
| `whole-object replacement` | PUT entity_settings | Forgotten fields are dropped |

---

## Notes

1. **Authentication**: All endpoints require authentication headers (typically Bearer token)
2. **Base URL**: Prepend your API base URL (e.g., `https://api.elitea.ai`) to all endpoints
3. **Project ID**: Replace `{projectId}` with your actual project ID
4. **Entity IDs**: Replace `{applicationId}`, `{toolId}`, etc. with actual entity IDs
5. **Naming Convention**: The API uses "prompt_lib" in paths for historical reasons (originally for prompt library)
6. **Error Handling**: All endpoints return standard error responses with appropriate HTTP status codes
7. **Rate Limiting**: Check response headers for rate limit information
8. **Validation**: Some fields are validated against JSON schemas before submission
9. **Caching**: Frontend uses RTK Query for automatic cache management and invalidation

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2026-02-13 | 1.0.0 | Initial comprehensive API documentation — Agents, Pipelines, Toolkits, Credentials, Secrets (entity CRUD). |
| 2026-05-25 | 2.0.0 | **Major extension.** Added §0 Conventions/Auth, §6 Conversations & Folders, §7 Participants & Entity Settings, §8 Messages/Attachments/Canvas, §9 Tool & Toolkit Discovery (incl. MCP), §10 Predict (agent execution), §11 Publish/Fork/Import-Export lifecycle, §12 Pipeline Triggers & Webhooks, §13 expanded Quick Reference, §14 Patterns & Gotchas. Reverse-engineered from `EliteaAI/elitea_core` (`api/v2/*.py`) and cross-validated against `EliteaAI/elitea-api-testing`. |

---

**For More Information:**
- v2 source (authoritative): `EliteaAI/elitea_core` repo, path `api/v2/*.py`
- Integration test payloads: `EliteaAI/elitea-api-testing` repo
- MCP tool schemas (the wrapper layer): `.github/agents/Elitea-MCP.agent.md`
- Frontend reference: `AlitaUI/src/api/`, `AlitaUI/src/hooks/`, `AlitaUI/src/pages/`
- Project documentation: see `CLAUDE.md` and `.claude/rules/`
