Title: GitHub - Portkey-AI/gateway: A blazing fast AI Gateway with integrated guardrails. Route to 200+ LLMs, 50+ AI Guardrails with 1 fast & friendly API.

URL Source: http://github.com/Portkey-AI/gateway

Markdown Content:
**English** | [中文](https://github.com/Portkey-AI/gateway/blob/main/.github/README.cn.md) | [日本語](https://github.com/Portkey-AI/gateway/blob/main/.github/README.jp.md)

Important

🚀 Gateway 2.0 (Pre-Release) Portkey's core enterprise gateway is merging into open-source with our 2.0 release. You can try the pre-release branch [here](https://github.com/portkey-ai/gateway/tree/2.0.0). Read more about what's next for Portkey in our [**Series A announcement**](https://portkey.wiki/rohit-a).

The [**AI Gateway**](https://portkey.wiki/gh-10) is designed for fast, reliable & secure routing to 1600+ language, vision, audio, and image models. It is a lightweight, open-source, and enterprise-ready solution that allows you to integrate with any language model in under 2 minutes.

*   **Blazing fast** (<1ms latency) with a tiny footprint (122kb)
*   **Battle tested**, with over 10B tokens processed everyday
*   **Enterprise-ready** with enhanced security, scale, and custom deployments

#### What can you do with the AI Gateway?

[](http://github.com/Portkey-AI/gateway#what-can-you-do-with-the-ai-gateway)
*   Integrate with any LLM in under 2 minutes - [Quickstart](http://github.com/Portkey-AI/gateway#quickstart-2-mins)
*   Prevent downtimes through **[automatic retries](https://portkey.wiki/gh-11)** and **[fallbacks](https://portkey.wiki/gh-12)**
*   Scale AI apps with **[load balancing](https://portkey.wiki/gh-13)** and **[conditional routing](https://portkey.wiki/gh-14)**
*   Protect your AI deployments with **[guardrails](https://portkey.wiki/gh-15)**
*   Go beyond text with **[multi-modal capabilities](https://portkey.wiki/gh-16)**
*   Explore **[agentic workflow](https://portkey.wiki/gh-17)** integrations
*   Manage MCP servers with enterprise auth & observability using **[MCP Gateway](https://portkey.ai/docs/product/mcp-gateway)**

Tip

Starring this repo helps more developers discover the AI Gateway 🙏🏻

[![Image 1: star-2](https://private-user-images.githubusercontent.com/134934501/365016161-53597dce-6333-4ecc-a154-eb05532954e4.gif?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3NzI2NDg5NjgsIm5iZiI6MTc3MjY0ODY2OCwicGF0aCI6Ii8xMzQ5MzQ1MDEvMzY1MDE2MTYxLTUzNTk3ZGNlLTYzMzMtNGVjYy1hMTU0LWViMDU1MzI5NTRlNC5naWY_WC1BbXotQWxnb3JpdGhtPUFXUzQtSE1BQy1TSEEyNTYmWC1BbXotQ3JlZGVudGlhbD1BS0lBVkNPRFlMU0E1M1BRSzRaQSUyRjIwMjYwMzA0JTJGdXMtZWFzdC0xJTJGczMlMkZhd3M0X3JlcXVlc3QmWC1BbXotRGF0ZT0yMDI2MDMwNFQxODI0MjhaJlgtQW16LUV4cGlyZXM9MzAwJlgtQW16LVNpZ25hdHVyZT04ZDA1YjRjZGNlZjgwMjYxN2ZhYjAxYTQzZDAxM2M4MTEzZTFlOTcyOWNhYjJmYTAyNWM3NDBlNTEzY2EyN2IzJlgtQW16LVNpZ25lZEhlYWRlcnM9aG9zdCJ9.AD4uPMaLoSgZ0UhLZF7qIFFQvusVxQCcHf9DeJxmdYQ)](https://private-user-images.githubusercontent.com/134934501/365016161-53597dce-6333-4ecc-a154-eb05532954e4.gif?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3NzI2NDg5NjgsIm5iZiI6MTc3MjY0ODY2OCwicGF0aCI6Ii8xMzQ5MzQ1MDEvMzY1MDE2MTYxLTUzNTk3ZGNlLTYzMzMtNGVjYy1hMTU0LWViMDU1MzI5NTRlNC5naWY_WC1BbXotQWxnb3JpdGhtPUFXUzQtSE1BQy1TSEEyNTYmWC1BbXotQ3JlZGVudGlhbD1BS0lBVkNPRFlMU0E1M1BRSzRaQSUyRjIwMjYwMzA0JTJGdXMtZWFzdC0xJTJGczMlMkZhd3M0X3JlcXVlc3QmWC1BbXotRGF0ZT0yMDI2MDMwNFQxODI0MjhaJlgtQW16LUV4cGlyZXM9MzAwJlgtQW16LVNpZ25hdHVyZT04ZDA1YjRjZGNlZjgwMjYxN2ZhYjAxYTQzZDAxM2M4MTEzZTFlOTcyOWNhYjJmYTAyNWM3NDBlNTEzY2EyN2IzJlgtQW16LVNpZ25lZEhlYWRlcnM9aG9zdCJ9.AD4uPMaLoSgZ0UhLZF7qIFFQvusVxQCcHf9DeJxmdYQ)

Quickstart (2 mins)
-------------------

[](http://github.com/Portkey-AI/gateway#quickstart-2-mins)
### 1. Setup your AI Gateway

[](http://github.com/Portkey-AI/gateway#1-setup-your-ai-gateway)

# Run the gateway locally (needs Node.js and npm)
npx @portkey-ai/gateway

> The Gateway is running on `http://localhost:8787/v1`
> 
> 
> The Gateway Console is running on `http://localhost:8787/public/`

 Deployment guides: [![Image 2](https://camo.githubusercontent.com/1e44c3d8239bf48da607f8792a1c729d4ee295071db44b5338b6f5e2ad3fb125/68747470733a2f2f63666173736574732e706f72746b65792e61692f6c6f676f2f6465772d636f6c6f722e737667) Portkey Cloud (Recommended)](https://portkey.wiki/gh-18)[![Image 3](https://camo.githubusercontent.com/1a9ef023f4536cde09cebde1be2e1723da3aa4afbf8d35d352bc49ee7acde036/68747470733a2f2f63646e2e73696d706c6569636f6e732e6f72672f646f636b65722f333737364142) Docker](https://github.com/Portkey-AI/gateway/blob/main/docs/installation-deployments.md#docker)[![Image 4](https://camo.githubusercontent.com/87affccef5167a490e9aeaf0401b56ab46dd185c3c87c0c51a8ac297e6b8cfcd/68747470733a2f2f63646e2e73696d706c6569636f6e732e6f72672f6e6f64652e6a732f333737364142) Node.js](https://github.com/Portkey-AI/gateway/blob/main/docs/installation-deployments.md#nodejs-server)[![Image 5](https://camo.githubusercontent.com/00367dbf18b2e8e7583bf49bb06967c4dc6c16e52177ad3689c26c95072a5b41/68747470733a2f2f63646e2e73696d706c6569636f6e732e6f72672f636c6f7564666c6172652f333737364142) Cloudflare](https://github.com/Portkey-AI/gateway/blob/main/docs/installation-deployments.md#cloudflare-workers)[![Image 6](https://camo.githubusercontent.com/57260786bd9abc6433c959bd8d5338298c06052eb530c1bc0a8fb7a021caf0a1/68747470733a2f2f63646e2e73696d706c6569636f6e732e6f72672f7265706c69742f333737364142) Replit](https://github.com/Portkey-AI/gateway/blob/main/docs/installation-deployments.md#replit)[Others...](https://github.com/Portkey-AI/gateway/blob/main/docs/installation-deployments.md)
### 2. Make your first request

[](http://github.com/Portkey-AI/gateway#2-make-your-first-request)

# pip install -qU portkey-ai

from portkey_ai import Portkey

# OpenAI compatible client
client = Portkey(
    provider="openai", # or 'anthropic', 'bedrock', 'groq', etc
    Authorization="sk-***" # the provider API key
)

# Make a request through your AI Gateway
client.chat.completions.create(
    messages=[{"role": "user", "content": "What's the weather like?"}],
    model="gpt-4o-mini"
)

Supported Libraries: [![Image 7](https://camo.githubusercontent.com/821d6e79f4bae3908cf09e7504d6ecf5b867be566a43067f3522aeac2faa199b/68747470733a2f2f63646e2e73696d706c6569636f6e732e6f72672f6a6176617363726970742f333737364142) JS](https://portkey.wiki/gh-19)[![Image 8](https://camo.githubusercontent.com/820e7e10fee68678f4d011e418f28be49a8eb8824a2fecceabac7bf98b5766ca/68747470733a2f2f63646e2e73696d706c6569636f6e732e6f72672f707974686f6e2f333737364142) Python](https://portkey.wiki/gh-20)[![Image 9](https://camo.githubusercontent.com/8e0d403e182ef63c8d81b296d7438ad44876a84ab4434e0fe80caaf20c9b1c3a/68747470733a2f2f63646e2e73696d706c6569636f6e732e6f72672f676e75626173682f333737364142) REST](https://portkey.sh/gh-84)[![Image 10](https://camo.githubusercontent.com/c0e3fc3ac99b7624576e9c3d2120e95871a2b036f815fe54374dcf01033046f2/68747470733a2f2f63646e2e73696d706c6569636f6e732e6f72672f6f70656e61692f333737364142) OpenAI SDKs](https://portkey.wiki/gh-21)[![Image 11](https://camo.githubusercontent.com/567b0fbbc055f147907f9301ba07a412e0e25395b965d8f5218407ae5e385622/68747470733a2f2f63646e2e73696d706c6569636f6e732e6f72672f6c616e67636861696e2f333737364142) Langchain](https://portkey.wiki/gh-22)[LlamaIndex](https://portkey.wiki/gh-23)[Autogen](https://portkey.wiki/gh-24)[CrewAI](https://portkey.wiki/gh-25)[More..](https://portkey.wiki/gh-26)

On the Gateway Console (`http://localhost:8787/public/`) you can see all of your local logs in one place.

[![Image 12: 397224910-362bc916-0fc9-43f1-a39e-4bd71aac4a3a.gif?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3NzI2NDg5NjgsIm5iZiI6MTc3MjY0ODY2OCwicGF0aCI6Ii8xMzQ5MzQ1MDEvMzk3MjI0OTEwLTM2MmJjOTE2LTBmYzktNDNmMS1hMzllLTRiZDcxYWFjNGEzYS5naWY_WC1BbXotQWxnb3JpdGhtPUFXUzQtSE1BQy1TSEEyNTYmWC1BbXotQ3JlZGVudGlhbD1BS0lBVkNPRFlMU0E1M1BRSzRaQSUyRjIwMjYwMzA0JTJGdXMtZWFzdC0xJTJGczMlMkZhd3M0X3JlcXVlc3QmWC1BbXotRGF0ZT0yMDI2MDMwNFQxODI0MjhaJlgtQW16LUV4cGlyZXM9MzAwJlgtQW16LVNpZ25hdHVyZT02YTQ2MjRhMzdiZTAxNTJhODExZDVjMTJmYzAxNjBmNjJlZTI0ZTA1MGMyODlkMTllZDkzOTcxYWU5NDgzOTQzJlgtQW16LVNpZ25lZEhlYWRlcnM9aG9zdCJ9.o-67h6GLb84yC6ht8Hj-Xn-1ePxLGUvUV7ZErZdXF9A](https://private-user-images.githubusercontent.com/134934501/397224910-362bc916-0fc9-43f1-a39e-4bd71aac4a3a.gif?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3NzI2NDg5NjgsIm5iZiI6MTc3MjY0ODY2OCwicGF0aCI6Ii8xMzQ5MzQ1MDEvMzk3MjI0OTEwLTM2MmJjOTE2LTBmYzktNDNmMS1hMzllLTRiZDcxYWFjNGEzYS5naWY_WC1BbXotQWxnb3JpdGhtPUFXUzQtSE1BQy1TSEEyNTYmWC1BbXotQ3JlZGVudGlhbD1BS0lBVkNPRFlMU0E1M1BRSzRaQSUyRjIwMjYwMzA0JTJGdXMtZWFzdC0xJTJGczMlMkZhd3M0X3JlcXVlc3QmWC1BbXotRGF0ZT0yMDI2MDMwNFQxODI0MjhaJlgtQW16LUV4cGlyZXM9MzAwJlgtQW16LVNpZ25hdHVyZT02YTQ2MjRhMzdiZTAxNTJhODExZDVjMTJmYzAxNjBmNjJlZTI0ZTA1MGMyODlkMTllZDkzOTcxYWU5NDgzOTQzJlgtQW16LVNpZ25lZEhlYWRlcnM9aG9zdCJ9.o-67h6GLb84yC6ht8Hj-Xn-1ePxLGUvUV7ZErZdXF9A)](https://private-user-images.githubusercontent.com/134934501/397224910-362bc916-0fc9-43f1-a39e-4bd71aac4a3a.gif?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3NzI2NDg5NjgsIm5iZiI6MTc3MjY0ODY2OCwicGF0aCI6Ii8xMzQ5MzQ1MDEvMzk3MjI0OTEwLTM2MmJjOTE2LTBmYzktNDNmMS1hMzllLTRiZDcxYWFjNGEzYS5naWY_WC1BbXotQWxnb3JpdGhtPUFXUzQtSE1BQy1TSEEyNTYmWC1BbXotQ3JlZGVudGlhbD1BS0lBVkNPRFlMU0E1M1BRSzRaQSUyRjIwMjYwMzA0JTJGdXMtZWFzdC0xJTJGczMlMkZhd3M0X3JlcXVlc3QmWC1BbXotRGF0ZT0yMDI2MDMwNFQxODI0MjhaJlgtQW16LUV4cGlyZXM9MzAwJlgtQW16LVNpZ25hdHVyZT02YTQ2MjRhMzdiZTAxNTJhODExZDVjMTJmYzAxNjBmNjJlZTI0ZTA1MGMyODlkMTllZDkzOTcxYWU5NDgzOTQzJlgtQW16LVNpZ25lZEhlYWRlcnM9aG9zdCJ9.o-67h6GLb84yC6ht8Hj-Xn-1ePxLGUvUV7ZErZdXF9A)
### 3. Routing & Guardrails

[](http://github.com/Portkey-AI/gateway#3-routing--guardrails)
`Configs` in the LLM gateway allow you to create routing rules, add reliability and setup guardrails.

config = {
  "retry": {"attempts": 5},

  "output_guardrails": [{
    "default.contains": {"operator": "none", "words": ["Apple"]},
    "deny": True
  }]
}

# Attach the config to the client
client = client.with_options(config=config)

client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Reply randomly with Apple or Bat"}]
)

# This would always response with "Bat" as the guardrail denies all replies containing "Apple". The retry config would retry 5 times before giving up.

[![Image 13: Request flow through Portkey's AI gateway with retries and guardrails](https://camo.githubusercontent.com/237a595b95fd5997e74d06c1d44943d2012b477c5b12c67368698e95f8e162b0/68747470733a2f2f706f72746b65792e61692f626c6f672f636f6e74656e742f696d616765732f73697a652f77313630302f323032342f31312f696d6167652d31352e706e67)](https://camo.githubusercontent.com/237a595b95fd5997e74d06c1d44943d2012b477c5b12c67368698e95f8e162b0/68747470733a2f2f706f72746b65792e61692f626c6f672f636f6e74656e742f696d616765732f73697a652f77313630302f323032342f31312f696d6167652d31352e706e67)

You can do a lot more stuff with configs in your AI gateway. [Jump to examples →](https://portkey.wiki/gh-27)

### Enterprise Version (Private deployments)

[](http://github.com/Portkey-AI/gateway#enterprise-version-private-deployments)
[![Image 14](https://camo.githubusercontent.com/7d6b54dc144129e078fd940e53bec230bd02d939d04d8322e54df7632584fe9d/68747470733a2f2f63666173736574732e706f72746b65792e61692f616d617a6f6e2d6c6f676f2e737667) AWS](https://portkey.wiki/gh-28)[![Image 15](https://camo.githubusercontent.com/487a0372b7b313676df189c9a88df51dab1830727aa91be1cbb08d6a5d2cc7c3/68747470733a2f2f63666173736574732e706f72746b65792e61692f617a7572652d6c6f676f2e737667) Azure](https://portkey.wiki/gh-29)[![Image 16](https://camo.githubusercontent.com/f6f5476be6d98d2c02bc003909d06959778f4a330a682a74a979a201aa7656f6/68747470733a2f2f63646e2e73696d706c6569636f6e732e6f72672f676f6f676c65636c6f75642f333737364142) GCP](https://portkey.wiki/gh-30)[![Image 17](https://camo.githubusercontent.com/7b6481a1bec4f7c17b7600ea9d1a1a2a8b5290d565012891be01594444851814/68747470733a2f2f63646e2e73696d706c6569636f6e732e6f72672f7265646861746f70656e73686966742f333737364142) OpenShift](https://portkey.wiki/gh-31)[![Image 18](https://camo.githubusercontent.com/480b40e668a93e9e08b41c17fb01da62d0e4ea5aea286f9f3c98f66750c643b8/68747470733a2f2f63646e2e73696d706c6569636f6e732e6f72672f6b756265726e657465732f333737364142) Kubernetes](https://portkey.wiki/gh-85)

The LLM Gateway's [enterprise version](https://portkey.wiki/gh-86) offers advanced capabilities for **org management**, **governance**, **security** and [more](https://portkey.wiki/gh-87) out of the box. [View Feature Comparison →](https://portkey.wiki/gh-32)

The enterprise deployment architecture for supported platforms is available here - [**Enterprise Private Cloud Deployments**](https://portkey.ai/docs/self-hosting/hybrid-deployments/architecture)

[![Image 19: Book an enterprise AI gateway demo](https://camo.githubusercontent.com/6dceb72fdda5ae2ae3eda07f4aaac4a299efc7a7fc4edd06e863d631a6a47820/68747470733a2f2f706f72746b65792e61692f626c6f672f636f6e74656e742f696d616765732f323032342f30382f4765742d4150492d4b65792d2d352d2e706e67)](https://portkey.sh/demo-13)

MCP Gateway
-----------

[](http://github.com/Portkey-AI/gateway#mcp-gateway)
[MCP Gateway](https://portkey.ai/docs/product/mcp-gateway) provides a centralized control plane for managing MCP (Model Context Protocol) servers across your organization.

*   **Authentication** — Single auth layer at the gateway. Users authenticate once; your MCP servers receive verified requests
*   **Access Control** — Control which teams and users can access which servers and tools. Revoke access instantly
*   **Observability** — Every tool call logged with full context: who called what, parameters, response, latency
*   **Identity Forwarding** — Forward user identity (email, team, roles) to MCP servers automatically

Works with Claude Desktop, Cursor, VS Code, and any MCP-compatible client. [Get started →](https://portkey.ai/docs/product/mcp-gateway/quickstart)

Core Features
-------------

[](http://github.com/Portkey-AI/gateway#core-features)
### Reliable Routing

[](http://github.com/Portkey-AI/gateway#reliable-routing)
*   [**Fallbacks**](https://portkey.wiki/gh-37): Fallback to another provider or model on failed requests using the LLM gateway. You can specify the errors on which to trigger the fallback. Improves reliability of your application.
*   [**Automatic Retries**](https://portkey.wiki/gh-38): Automatically retry failed requests up to 5 times. An exponential backoff strategy spaces out retry attempts to prevent network overload.
*   [**Load Balancing**](https://portkey.wiki/gh-39): Distribute LLM requests across multiple API keys or AI providers with weights to ensure high availability and optimal performance.
*   [**Request Timeouts**](https://portkey.wiki/gh-40): Manage unruly LLMs & latencies by setting up granular request timeouts, allowing automatic termination of requests that exceed a specified duration.
*   [**Multi-modal LLM Gateway**](https://portkey.wiki/gh-41): Call vision, audio (text-to-speech & speech-to-text), and image generation models from multiple providers — all using the familiar OpenAI signature
*   [**Realtime APIs**](https://portkey.wiki/gh-42): Call realtime APIs launched by OpenAI through the integrate websockets server.

### Security & Accuracy

[](http://github.com/Portkey-AI/gateway#security--accuracy)
*   [**Guardrails**](https://portkey.wiki/gh-88): Verify your LLM inputs and outputs to adhere to your specified checks. Choose from the 40+ pre-built guardrails to ensure compliance with security and accuracy standards. You can [bring your own guardrails](https://portkey.wiki/gh-43) or choose from our [many partners](https://portkey.wiki/gh-44).
*   [**Secure Key Management**](https://portkey.wiki/gh-45): Use your own keys or generate virtual keys on the fly.
*   [**Role-based access control**](https://portkey.wiki/gh-46): Granular access control for your users, workspaces and API keys.
*   [**Compliance & Data Privacy**](https://portkey.wiki/gh-47): The AI gateway is SOC2, HIPAA, GDPR, and CCPA compliant.

### Cost Management

[](http://github.com/Portkey-AI/gateway#cost-management)
*   [**Smart caching**](https://portkey.wiki/gh-48): Cache responses from LLMs to reduce costs and improve latency. Supports simple and semantic* caching.
*   [**Usage analytics**](https://portkey.wiki/gh-49): Monitor and analyze your AI and LLM usage, including request volume, latency, costs and error rates.
*   [**Provider optimization***](https://portkey.wiki/gh-89): Automatically switch to the most cost-effective provider based on usage patterns and pricing models.

### Collaboration & Workflows

[](http://github.com/Portkey-AI/gateway#collaboration--workflows)
*   [**Agents Support**](https://portkey.ai/docs/integrations/agents): Seamlessly integrate with popular agent frameworks to build complex AI applications. The gateway seamlessly integrates with [Autogen](https://portkey.wiki/gh-50), [CrewAI](https://portkey.wiki/gh-51), [LangChain](https://portkey.wiki/gh-52), [LlamaIndex](https://portkey.wiki/gh-53), [Phidata](https://portkey.wiki/gh-54), [Control Flow](https://portkey.wiki/gh-55), and even [Custom Agents](https://portkey.wiki/gh-56).
*   [**Prompt Template Management***](https://portkey.wiki/gh-57): Create, manage and version your prompt templates collaboratively through a universal prompt playground. 

 *Available in hosted and enterprise versions 
Portkey Models
--------------

[](http://github.com/Portkey-AI/gateway#portkey-models)
Open-source LLM pricing database for 40+ providers - used by the Gateway for cost tracking.

[GitHub](https://github.com/Portkey-AI/models) | [Model Explorer](https://portkey.ai/models)

Cookbooks
---------

[](http://github.com/Portkey-AI/gateway#cookbooks)
### ☄️ Trending

[](http://github.com/Portkey-AI/gateway#%EF%B8%8F-trending)
*   Use models from [Nvidia NIM](https://github.com/Portkey-AI/gateway/blob/main/cookbook/providers/nvidia.ipynb) with AI Gateway
*   Monitor [CrewAI Agents](https://github.com/Portkey-AI/gateway/blob/main/cookbook/monitoring-agents/CrewAI_with_Telemetry.ipynb) with Portkey!
*   Comparing [Top 10 LMSYS Models](https://github.com/Portkey-AI/gateway/blob/main/cookbook/use-cases/LMSYS%20Series/comparing-top10-LMSYS-models-with-Portkey.ipynb) with AI Gateway.

### 🚨 Latest

[](http://github.com/Portkey-AI/gateway#-latest)
*   [Create Synthetic Datasets using Nemotron](https://github.com/Portkey-AI/gateway/blob/main/cookbook/use-cases/Nemotron_GPT_Finetuning_Portkey.ipynb)
*   [Use the LLM Gateway with Vercel's AI SDK](https://github.com/Portkey-AI/gateway/blob/main/cookbook/integrations/vercel-ai.md)
*   [Monitor Llama Agents with Portkey's LLM Gateway](https://github.com/Portkey-AI/gateway/blob/main/cookbook/monitoring-agents/Llama_Agents_with_Telemetry.ipynb)

Supported Providers
-------------------

[](http://github.com/Portkey-AI/gateway#supported-providers)
Explore Gateway integrations with [45+ providers](https://portkey.wiki/gh-59) and [8+ agent frameworks](https://portkey.wiki/gh-90).

|  | Provider | Support | Stream |
| --- | --- | --- | --- |
| [![Image 20](https://github.com/Portkey-AI/gateway/raw/main/docs/images/openai.png)](https://github.com/Portkey-AI/gateway/blob/main/docs/images/openai.png) | [OpenAI](https://portkey.wiki/gh-60) | ✅ | ✅ |
| [![Image 21](https://github.com/Portkey-AI/gateway/raw/main/docs/images/azure.png)](https://github.com/Portkey-AI/gateway/blob/main/docs/images/azure.png) | [Azure OpenAI](https://portkey.wiki/gh-61) | ✅ | ✅ |
| [![Image 22](https://github.com/Portkey-AI/gateway/raw/main/docs/images/anyscale.png)](https://github.com/Portkey-AI/gateway/blob/main/docs/images/anyscale.png) | [Anyscale](https://portkey.wiki/gh-62) | ✅ | ✅ |
| [![Image 23](https://camo.githubusercontent.com/05bbb6251f5adf42e483b6c1f7f4ad94a9a25bf6d9f97cdf1682b3b6e66162a6/68747470733a2f2f75706c6f61642e77696b696d656469612e6f72672f77696b6970656469612f636f6d6d6f6e732f322f32642f476f6f676c652d66617669636f6e2d323031352e706e67)](https://camo.githubusercontent.com/05bbb6251f5adf42e483b6c1f7f4ad94a9a25bf6d9f97cdf1682b3b6e66162a6/68747470733a2f2f75706c6f61642e77696b696d656469612e6f72672f77696b6970656469612f636f6d6d6f6e732f322f32642f476f6f676c652d66617669636f6e2d323031352e706e67) | [Google Gemini](https://portkey.wiki/gh-63) | ✅ | ✅ |
| [![Image 24](https://github.com/Portkey-AI/gateway/raw/main/docs/images/anthropic.png)](https://github.com/Portkey-AI/gateway/blob/main/docs/images/anthropic.png) | [Anthropic](https://portkey.wiki/gh-64) | ✅ | ✅ |
| [![Image 25](https://github.com/Portkey-AI/gateway/raw/main/docs/images/cohere.png)](https://github.com/Portkey-AI/gateway/blob/main/docs/images/cohere.png) | [Cohere](https://portkey.wiki/gh-65) | ✅ | ✅ |
| [![Image 26](https://camo.githubusercontent.com/e20648e562d1c08e8cd7a17d32ae0e98adc3837c3e7122c96322428739caefb1/68747470733a2f2f6173736574732d676c6f62616c2e776562736974652d66696c65732e636f6d2f3634663666326330653366346335613931633165383233612f3635343639336435363934393439313263666330633064345f66617669636f6e2e737667)](https://camo.githubusercontent.com/e20648e562d1c08e8cd7a17d32ae0e98adc3837c3e7122c96322428739caefb1/68747470733a2f2f6173736574732d676c6f62616c2e776562736974652d66696c65732e636f6d2f3634663666326330653366346335613931633165383233612f3635343639336435363934393439313263666330633064345f66617669636f6e2e737667) | [Together AI](https://portkey.wiki/gh-66) | ✅ | ✅ |
| [![Image 27](https://camo.githubusercontent.com/832c24d93d4a3d8459a1764ba7e071173bc88615d337879676e9f75988f913d8/68747470733a2f2f7777772e706572706c65786974792e61692f66617669636f6e2e737667)](https://camo.githubusercontent.com/832c24d93d4a3d8459a1764ba7e071173bc88615d337879676e9f75988f913d8/68747470733a2f2f7777772e706572706c65786974792e61692f66617669636f6e2e737667) | [Perplexity](https://portkey.wiki/gh-67) | ✅ | ✅ |
| [![Image 28](https://camo.githubusercontent.com/142e59a6ad6d6709de1e2722ca39b781e3b4c620355282d26063a2120b37c010/68747470733a2f2f646f63732e6d69737472616c2e61692f696d672f66617669636f6e2e69636f)](https://camo.githubusercontent.com/142e59a6ad6d6709de1e2722ca39b781e3b4c620355282d26063a2120b37c010/68747470733a2f2f646f63732e6d69737472616c2e61692f696d672f66617669636f6e2e69636f) | [Mistral](https://portkey.wiki/gh-68) | ✅ | ✅ |
| [![Image 29](https://camo.githubusercontent.com/f01ee03f9c125b4426910cbbb35ab42645d29b38ee56672740642f56d3a0ed13/68747470733a2f2f646f63732e6e6f6d69632e61692f696d672f6e6f6d69632d6c6f676f2e706e67)](https://camo.githubusercontent.com/f01ee03f9c125b4426910cbbb35ab42645d29b38ee56672740642f56d3a0ed13/68747470733a2f2f646f63732e6e6f6d69632e61692f696d672f6e6f6d69632d6c6f676f2e706e67) | [Nomic](https://portkey.wiki/gh-69) | ✅ | ✅ |
| [![Image 30](https://camo.githubusercontent.com/945aac80f0a39fb4c9ff9ace8e183dfe9c162b9db7b1072583cb116461cfdc6d/68747470733a2f2f66696c65732e726561646d652e696f2f643338613233652d736d616c6c2d73747564696f2d66617669636f6e2e706e67)](https://camo.githubusercontent.com/945aac80f0a39fb4c9ff9ace8e183dfe9c162b9db7b1072583cb116461cfdc6d/68747470733a2f2f66696c65732e726561646d652e696f2f643338613233652d736d616c6c2d73747564696f2d66617669636f6e2e706e67) | [AI21](https://portkey.wiki/gh-91) | ✅ | ✅ |
| [![Image 31](https://camo.githubusercontent.com/548a4b7aa90ad8c88f207cdd36d5c9350e3384fe0f4cb20ad76075ce678d9cf4/68747470733a2f2f706c6174666f726d2e73746162696c6974792e61692f736d616c6c2d6c6f676f2d707572706c652e737667)](https://camo.githubusercontent.com/548a4b7aa90ad8c88f207cdd36d5c9350e3384fe0f4cb20ad76075ce678d9cf4/68747470733a2f2f706c6174666f726d2e73746162696c6974792e61692f736d616c6c2d6c6f676f2d707572706c652e737667) | [Stability AI](https://portkey.wiki/gh-71) | ✅ | ✅ |
| [![Image 32](https://camo.githubusercontent.com/d5bdafd4451c1ff1fcc2bbe88d3da7a7e1d2f9ac88971d5d6f78ef1ae9ed87f9/68747470733a2f2f64656570696e6672612e636f6d2f5f6e6578742f7374617469632f6d656469612f6c6f676f2e34613033666433642e737667)](https://camo.githubusercontent.com/d5bdafd4451c1ff1fcc2bbe88d3da7a7e1d2f9ac88971d5d6f78ef1ae9ed87f9/68747470733a2f2f64656570696e6672612e636f6d2f5f6e6578742f7374617469632f6d656469612f6c6f676f2e34613033666433642e737667) | [DeepInfra](https://portkey.sh/gh-92) | ✅ | ✅ |
| [![Image 33](https://camo.githubusercontent.com/a07b906d6c455840ca72fefbc46eab4f1eb9824d3ac09e8f15d7f7a52d98f058/68747470733a2f2f6f6c6c616d612e636f6d2f7075626c69632f6f6c6c616d612e706e67)](https://camo.githubusercontent.com/a07b906d6c455840ca72fefbc46eab4f1eb9824d3ac09e8f15d7f7a52d98f058/68747470733a2f2f6f6c6c616d612e636f6d2f7075626c69632f6f6c6c616d612e706e67) | [Ollama](https://portkey.wiki/gh-72) | ✅ | ✅ |
| [![Image 34](https://camo.githubusercontent.com/d030a7fb045c73ff553d5fa2074c11a539e4e9066d1f7375631ccb6e5d266ab2/68747470733a2f2f6e6f766974612e61692f66617669636f6e2e69636f)](https://camo.githubusercontent.com/d030a7fb045c73ff553d5fa2074c11a539e4e9066d1f7375631ccb6e5d266ab2/68747470733a2f2f6e6f766974612e61692f66617669636f6e2e69636f) | [Novita AI](https://portkey.wiki/gh-73) | ✅ | ✅ |

> [View the complete list of 200+ supported models here](https://portkey.wiki/gh-74)

Agents
------

[](http://github.com/Portkey-AI/gateway#agents)
Gateway seamlessly integrates with popular agent frameworks. [Read the documentation here](https://portkey.wiki/gh-75).

| Framework | Call 200+ LLMs | Advanced Routing | Caching | Logging & Tracing* | Observability* | Prompt Management* |
| --- | --- | --- | --- | --- | --- | --- |
| [Autogen](https://portkey.wiki/gh-93) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| [CrewAI](https://portkey.wiki/gh-94) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| [LangChain](https://portkey.wiki/gh-95) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| [Phidata](https://portkey.wiki/gh-96) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| [Llama Index](https://portkey.wiki/gh-97) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| [Control Flow](https://portkey.wiki/gh-98) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| [Build Your Own Agents](https://portkey.wiki/gh-99) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| [![Image 35](https://camo.githubusercontent.com/61d4e812bf208013826b78dec0706cd9445d03705771d474ea9cfdd64ee0c0da/68747470733a2f2f696f2e6e65742f66617669636f6e2e69636f)](https://camo.githubusercontent.com/61d4e812bf208013826b78dec0706cd9445d03705771d474ea9cfdd64ee0c0da/68747470733a2f2f696f2e6e65742f66617669636f6e2e69636f) | [IO Intelligence](https://io.net/intelligence) | ✅ | ✅ |  |  |  |

*Available on the [hosted app](https://portkey.wiki/gh-76). For detailed documentation [click here](https://portkey.wiki/gh-100).

Gateway Enterprise Version
--------------------------

[](http://github.com/Portkey-AI/gateway#gateway-enterprise-version)
Make your AI app more reliable and forward compatible, while ensuring complete data security and privacy.

✅ Secure Key Management - for role-based access control and tracking 

 ✅ Simple & Semantic Caching - to serve repeat queries faster & save costs 

 ✅ Access Control & Inbound Rules - to control which IPs and Geos can connect to your deployments 

 ✅ PII Redaction - to automatically remove sensitive data from your requests to prevent indavertent exposure 

 ✅ SOC2, ISO, HIPAA, GDPR Compliances - for best security practices 

 ✅ Professional Support - along with feature prioritization

[Schedule a call to discuss enterprise deployments](https://portkey.sh/demo-13)

Contributing
------------

[](http://github.com/Portkey-AI/gateway#contributing)
The easiest way to contribute is to pick an issue with the `good first issue` tag 💪. Read the contribution guidelines [here](https://github.com/Portkey-AI/gateway/blob/main/.github/CONTRIBUTING.md).

Bug Report? [File here](https://portkey.wiki/gh-78) | Feature Request? [File here](https://portkey.wiki/gh-78)

### Getting Started with the Community

[](http://github.com/Portkey-AI/gateway#getting-started-with-the-community)
Join our weekly AI Engineering Hours every Friday (8 AM PT) to:

*   Meet other contributors and community members
*   Learn advanced Gateway features and implementation patterns
*   Share your experiences and get help
*   Stay updated with the latest development priorities

[Join the next session →](https://portkey.wiki/gh-101) | [Meeting notes](https://portkey.wiki/gh-102)

Community
---------

[](http://github.com/Portkey-AI/gateway#community)
Join our growing community around the world, for help, ideas, and discussions on AI.

*   View our official [Blog](https://portkey.wiki/gh-78)
*   Chat with us on [Discord](https://portkey.wiki/community)
*   Follow us on [Twitter](https://portkey.wiki/gh-79)
*   Connect with us on [LinkedIn](https://portkey.wiki/gh-80)
*   Read the documentation in [Japanese](https://github.com/Portkey-AI/gateway/blob/main/.github/README.jp.md)
*   Visit us on [YouTube](https://portkey.wiki/gh-103)
*   Join our [Dev community](https://portkey.wiki/gh-82)

[![Image 36: Rubeus Social Share (4)](https://private-user-images.githubusercontent.com/971978/294914756-89d6f0af-a95d-4402-b451-14764c40d03f.png?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3NzI2NDg5NjgsIm5iZiI6MTc3MjY0ODY2OCwicGF0aCI6Ii85NzE5NzgvMjk0OTE0NzU2LTg5ZDZmMGFmLWE5NWQtNDQwMi1iNDUxLTE0NzY0YzQwZDAzZi5wbmc_WC1BbXotQWxnb3JpdGhtPUFXUzQtSE1BQy1TSEEyNTYmWC1BbXotQ3JlZGVudGlhbD1BS0lBVkNPRFlMU0E1M1BRSzRaQSUyRjIwMjYwMzA0JTJGdXMtZWFzdC0xJTJGczMlMkZhd3M0X3JlcXVlc3QmWC1BbXotRGF0ZT0yMDI2MDMwNFQxODI0MjhaJlgtQW16LUV4cGlyZXM9MzAwJlgtQW16LVNpZ25hdHVyZT1hYWEzYmE3ZTUxMzFhMzZmYzNmMDgxYTE5Y2ZhNGY0ODk3YjNhNDdhYWJiNWMxOWZkMGI4NGY3MzlhYzFiYmYwJlgtQW16LVNpZ25lZEhlYWRlcnM9aG9zdCJ9.tDbyB6evdBFyjffY9AoqnC1CSwk6qnSkJSofwlI0Cxo)](https://private-user-images.githubusercontent.com/971978/294914756-89d6f0af-a95d-4402-b451-14764c40d03f.png?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3NzI2NDg5NjgsIm5iZiI6MTc3MjY0ODY2OCwicGF0aCI6Ii85NzE5NzgvMjk0OTE0NzU2LTg5ZDZmMGFmLWE5NWQtNDQwMi1iNDUxLTE0NzY0YzQwZDAzZi5wbmc_WC1BbXotQWxnb3JpdGhtPUFXUzQtSE1BQy1TSEEyNTYmWC1BbXotQ3JlZGVudGlhbD1BS0lBVkNPRFlMU0E1M1BRSzRaQSUyRjIwMjYwMzA0JTJGdXMtZWFzdC0xJTJGczMlMkZhd3M0X3JlcXVlc3QmWC1BbXotRGF0ZT0yMDI2MDMwNFQxODI0MjhaJlgtQW16LUV4cGlyZXM9MzAwJlgtQW16LVNpZ25hdHVyZT1hYWEzYmE3ZTUxMzFhMzZmYzNmMDgxYTE5Y2ZhNGY0ODk3YjNhNDdhYWJiNWMxOWZkMGI4NGY3MzlhYzFiYmYwJlgtQW16LVNpZ25lZEhlYWRlcnM9aG9zdCJ9.tDbyB6evdBFyjffY9AoqnC1CSwk6qnSkJSofwlI0Cxo)
