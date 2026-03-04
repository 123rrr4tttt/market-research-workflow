Title: GitHub - Helicone/ai-gateway: The fastest, lightest, and easiest-to-integrate AI gateway on the market. Fully open-sourced.

URL Source: http://github.com/Helicone/ai-gateway

Markdown Content:
[![Image 1: Helicone AI Gateway](https://camo.githubusercontent.com/9fc233caa80aa7a8b0528b929d0dbf7579e7803043c2df624ed07fd7782ff3c1/68747470733a2f2f6d61726b6574696e672d6173736574732d68656c69636f6e652e73332e75732d776573742d322e616d617a6f6e6177732e636f6d2f6769746875622d772533416c6f676f2e706e67)](https://camo.githubusercontent.com/9fc233caa80aa7a8b0528b929d0dbf7579e7803043c2df624ed07fd7782ff3c1/68747470733a2f2f6d61726b6574696e672d6173736574732d68656c69636f6e652e73332e75732d776573742d322e616d617a6f6e6177732e636f6d2f6769746875622d772533416c6f676f2e706e67)

[![Image 2: GitHub stars](https://camo.githubusercontent.com/3d309886e72906a50dab2cc304a1d3585a53000f368a6a99d246976f17ea2b47/68747470733a2f2f696d672e736869656c64732e696f2f6769746875622f73746172732f48656c69636f6e652f61692d676174657761793f7374796c653d666f722d7468652d6261646765)](https://github.com/helicone/ai-gateway/)[![Image 3: Downloads](https://camo.githubusercontent.com/d7c5afee503e36b04bd6c35a615f663f248b66324d5799549c2cf9058808daf8/68747470733a2f2f696d672e736869656c64732e696f2f6769746875622f646f776e6c6f6164732f48656c69636f6e652f61692d676174657761792f746f74616c3f7374796c653d666f722d7468652d6261646765)](https://github.com/helicone/aia-gateway/releases)[![Image 4: Docker pulls](https://camo.githubusercontent.com/24a7d8c276d8062a61fca396ab8a67ee87b9ee98689fffb2bb933db0f5d98263/68747470733a2f2f696d672e736869656c64732e696f2f646f636b65722f70756c6c732f68656c69636f6e652f61692d676174657761793f7374796c653d666f722d7468652d6261646765)](https://hub.docker.com/r/helicone/ai-gateway)[![Image 5: License](https://camo.githubusercontent.com/677aed8b4fa6e19d2975aaf2c39ee3a3dcef55198641f0861e07947179546aa4/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f6c6963656e73652d4150414348452d677265656e3f7374796c653d666f722d7468652d6261646765)](https://github.com/Helicone/ai-gateway/blob/main/LICENSE)[![Image 6: Public Beta](https://camo.githubusercontent.com/1d96a03712eb939e7a1fc24003186620782062c1ca2b595dc9bd6b5665374d3b/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f7374617475732d5075626c6963253230426574612d6f72616e67653f7374796c653d666f722d7468652d6261646765)](https://github.com/helicone/ai-gateway)

**The fastest, lightest, and easiest-to-integrate AI Gateway on the market.**

_Built by the team at [Helicone](https://helicone.ai/), open-sourced for the community._

[🚀 Quick Start](https://docs.helicone.ai/ai-gateway/quickstart) • [📖 Docs](https://docs.helicone.ai/ai-gateway/introduction) • [💬 Discord](https://discord.gg/7aSCGCGUeu) • [🌐 Website](https://helicone.ai/)

* * *

### 🚆 1 API. 100+ models.

[](http://github.com/Helicone/ai-gateway#-1-api-100-models)
**Open-source, lightweight, and built on Rust.**

Handle hundreds of models and millions of LLM requests with minimal latency and maximum reliability.

The NGINX of LLMs.

* * *

👩🏻‍💻 Set up in seconds
-------------------------

[](http://github.com/Helicone/ai-gateway#%E2%80%8D-set-up-in-seconds)
### With the cloud hosted AI Gateway

[](http://github.com/Helicone/ai-gateway#with-the-cloud-hosted-ai-gateway)

from openai import OpenAI

client = OpenAI(
  api_key="YOUR_HELICONE_API_KEY",
  base_url="https://ai-gateway.helicone.ai/ai",
)

completion = client.chat.completions.create(
  model="openai/gpt-4o-mini", # or 100+ models
  messages=[
    {
      "role": "user",
      "content": "Hello, how are you?"
    }
  ]
)

_-- For custom config, check out our [configuration guide](https://docs.helicone.ai/ai-gateway/config) and the [providers we support](https://github.com/Helicone/ai-gateway/blob/main/ai-gateway/config/embedded/providers.yaml)._

* * *

Why Helicone AI Gateway?
------------------------

[](http://github.com/Helicone/ai-gateway#why-helicone-ai-gateway)
#### 🌐 **Unified interface**

[](http://github.com/Helicone/ai-gateway#-unified-interface)
Request **any LLM provider** using familiar OpenAI syntax. Stop rewriting integrations—use one API for OpenAI, Anthropic, Google, AWS Bedrock, and [20+ more providers](https://docs.helicone.ai/ai-gateway/providers).

#### ⚡ **Smart provider selection**

[](http://github.com/Helicone/ai-gateway#-smart-provider-selection)
**Smart Routing** to always hit the fastest, cheapest, or most reliable option, and always aware of provider uptimes and your rate limits. Built-in strategies include model-based latency routing (fastest model), provider latency-based P2C + PeakEWMA (fastest provider), weighted distribution (based on model weight), and cost optimization (cheapest option).

#### 💰 **Control your spending**

[](http://github.com/Helicone/ai-gateway#-control-your-spending)
**Rate limit** to prevent runaway costs and usage abuse. Set limits per user, team, or globally with support for request counts, token usage, and dollar amounts.

#### 🚀 **Improve performance**

[](http://github.com/Helicone/ai-gateway#-improve-performance)
**Cache responses** to reduce costs and latency by up to 95%. Supports Redis and S3 backends with intelligent cache invalidation.

#### 📊 **Simplified tracing**

[](http://github.com/Helicone/ai-gateway#-simplified-tracing)
Monitor performance and debug issues with built-in Helicone integration, plus OpenTelemetry support for **logs, metrics, and traces**.

#### ☁️ **One-click deployment**

[](http://github.com/Helicone/ai-gateway#%EF%B8%8F-one-click-deployment)
Use our [cloud-hosted AI Gateway](https://us.helicone.ai/gateway) or deploy it to your own infrastructure in seconds by using **Docker** or following any of our [deployment guides here](https://docs.helicone.ai/ai-gateway/deployment/overview).

Launch.Final.1.1.1.mp4

* * *

⚡ Scalable for production
-------------------------

[](http://github.com/Helicone/ai-gateway#-scalable-for-production)
| Metric | Helicone AI Gateway | Typical Setup |
| --- | --- | --- |
| **P95 Latency** | <5ms | ~60-100ms |
| **Memory Usage** | ~64MB | ~512MB |
| **Requests/sec** | ~3,000 | ~500 |
| **Binary Size** | ~30MB | ~200MB |
| **Cold Start** | ~100ms | ~2s |

_Note: See [benchmarks/README.md](https://github.com/Helicone/ai-gateway/blob/main/benchmarks/README.md) for detailed benchmarking methodology and results._

* * *

🎥 Demo
-------

[](http://github.com/Helicone/ai-gateway#-demo)

AI.Gateway.Demo.mp4

* * *

🏗️ How it works
----------------

[](http://github.com/Helicone/ai-gateway#%EF%B8%8F-how-it-works)

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Your App      │───▶│ Helicone AI     │───▶│  LLM Providers  │
│                 │    │ Gateway         │    │                 │
│ OpenAI SDK      │    │                 │    │ • OpenAI        │
│ (any language)  │    │ • Load Balance  │    │ • Anthropic     │
│                 │    │ • Rate Limit    │    │ • AWS Bedrock   │
│                 │    │ • Cache         │    │ • Google Vertex │
│                 │    │ • Trace         │    │ • 20+ more      │
│                 │    │ • Fallbacks     │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                               │
                               ▼
                      ┌─────────────────┐
                      │ Helicone        │
                      │ Observability   │
                      │                 │
                      │ • Dashboard     │
                      │ • Observability │
                      │ • Monitoring    │
                      │ • Debugging     │
                      └─────────────────┘
```

* * *

⚙️ Custom configuration
-----------------------

[](http://github.com/Helicone/ai-gateway#%EF%B8%8F-custom-configuration)
### Cloud hosted router configuration

[](http://github.com/Helicone/ai-gateway#cloud-hosted-router-configuration)
For the cloud hosted router, we provide a configuration wizard in the UI to help you setup your router without the need for any YAML engineering.

For complete reference of our configuration options, check out our [configuration reference](https://docs.helicone.ai/ai-gateway/config) and the [providers we support](https://github.com/Helicone/ai-gateway/blob/main/ai-gateway/config/embedded/providers.yaml).

* * *

📚 Migration guide
------------------

[](http://github.com/Helicone/ai-gateway#-migration-guide)
### From OpenAI (Python)

[](http://github.com/Helicone/ai-gateway#from-openai-python)

from openai import OpenAI

client = OpenAI(
- api_key=os.getenv("OPENAI_API_KEY")
+ api_key="placeholder-api-key" # Gateway handles API keys
+ base_url="http://localhost:8080/router/your-router-name"
)

response = client.chat.completions.create(
- model="gpt-4o-mini",
+ model="openai/gpt-4o-mini", # or 100+ models
    messages=[{"role": "user", "content": "Hello!"}]
)

### From OpenAI (TypeScript)

[](http://github.com/Helicone/ai-gateway#from-openai-typescript)

import { OpenAI } from "openai";

const client = new OpenAI({
- apiKey: os.getenv("OPENAI_API_KEY")
+ apiKey: "placeholder-api-key", // Gateway handles API keys
+ baseURL: "http://localhost:8080/router/your-router-name",
});

const response = await client.chat.completions.create({
- model: "gpt-4o",
+ model: "openai/gpt-4o",
  messages: [{ role: "user", content: "Hello from Helicone AI Gateway!" }],
});

* * *

Self-host the AI Gateway
------------------------

[](http://github.com/Helicone/ai-gateway#self-host-the-ai-gateway)
The option might be best for you if you are extremely latency sensitive, or want to avoid a cloud offering and would prefer to self host the gateway.

### Run the AI Gateway locally

[](http://github.com/Helicone/ai-gateway#run-the-ai-gateway-locally)
1.   Set up your `.env` file with your `PROVIDER_API_KEY`s

OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key

1.   Run locally in your terminal

npx @helicone/ai-gateway@latest

1.   Make your requests using any OpenAI SDK:

from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8080/ai",
    # Gateway handles API keys, so this only needs to be 
    # set to a valid Helicone API key if authentication is enabled.
    api_key="placeholder-api-key"
)

# Route to any LLM provider through the same interface, we handle the rest.
response = client.chat.completions.create(
    model="anthropic/claude-3-5-sonnet",  # Or other 100+ models..
    messages=[{"role": "user", "content": "Hello from Helicone AI Gateway!"}]
)

**That's it.** No new SDKs to learn, no integrations to maintain. Fully-featured and open-sourced.

_-- For custom config, check out our [configuration guide](https://docs.helicone.ai/ai-gateway/config) and the [providers we support](https://github.com/Helicone/ai-gateway/blob/main/ai-gateway/config/embedded/providers.yaml)._

### Self hosted configuration customization

[](http://github.com/Helicone/ai-gateway#self-hosted-configuration-customization)
If you are self hosting the gateway and would like to configure different routing strategies, you may follow the below steps:

#### 1. Set up your environment variables

[](http://github.com/Helicone/ai-gateway#1-set-up-your-environment-variables)
Include your `PROVIDER_API_KEY`s in your `.env` file.

If you would like to enable authentication, set the `HELICONE_CONTROL_PLANE_API_KEY` variable as well.

OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
HELICONE_CONTROL_PLANE_API_KEY=sk-...

#### 2. Customize your config file

[](http://github.com/Helicone/ai-gateway#2-customize-your-config-file)
_Note: This is a sample `config.yaml` file. Please refer to our [configuration guide](https://docs.helicone.ai/ai-gateway/config) for the full list of options, examples, and defaults._ _See our [full provider list here.](https://github.com/Helicone/ai-gateway/blob/main/ai-gateway/config/embedded/providers.yaml)_

helicone: # Include your HELICONE_API_KEY in your .env file
  features: all

cache-store:
  type: in-memory

global: # Global settings for all routers
  cache:
    directive: "max-age=3600, max-stale=1800"

routers:
  your-router-name: # Single router configuration
    load-balance:
      chat:
        strategy: model-latency
        models:
          - openai/gpt-4o-mini
          - anthropic/claude-3-7-sonnet
    rate-limit:
      per-api-key:
        capacity: 1000
        refill-frequency: 1m # 1000 requests per minute

#### 3. Run with your custom configuration

[](http://github.com/Helicone/ai-gateway#3-run-with-your-custom-configuration)

npx @helicone/ai-gateway@latest --config config.yaml

#### 4. Make your requests

[](http://github.com/Helicone/ai-gateway#4-make-your-requests)

from openai import OpenAI
import os

helicone_api_key = os.getenv("HELICONE_API_KEY")

client = OpenAI(
    base_url="http://localhost:8080/router/your-router-name",
    api_key=helicone_api_key
)

# Route to any LLM provider through the same interface, we handle the rest.
response = client.chat.completions.create(
    model="anthropic/claude-3-5-sonnet",  # Or other 100+ models..
    messages=[{"role": "user", "content": "Hello from Helicone AI Gateway!"}]
)

For a complete guide on self-hosting options, including Docker deployment, Kubernetes, and cloud platforms, see our [deployment guides](https://docs.helicone.ai/ai-gateway/deployment/overview).

* * *

📚 Resources
------------

[](http://github.com/Helicone/ai-gateway#-resources)
### Documentation

[](http://github.com/Helicone/ai-gateway#documentation)
*   📖 **[Full Documentation](https://docs.helicone.ai/ai-gateway/introduction)** - Complete guides and API reference
*   🚀 **[Quickstart Guide](https://docs.helicone.ai/ai-gateway/quickstart)** - Get up and running in 1 minute
*   🔬 **[Advanced Configurations](https://docs.helicone.ai/ai-gateway/config)** - Configuration reference & examples

### Community

[](http://github.com/Helicone/ai-gateway#community)
*   💬 **[Discord Server](https://discord.gg/7aSCGCGUeu)** - Our community of passionate AI engineers
*   🐙 **[GitHub Discussions](https://github.com/helicone/ai-gateway/discussions)** - Q&A and feature requests
*   🐦 **[Twitter](https://twitter.com/helicone_ai)** - Latest updates and announcements
*   📧 **[Newsletter](https://helicone.ai/email-signup)** - Tips and tricks to deploying AI applications

### Support

[](http://github.com/Helicone/ai-gateway#support)
*   🎫 **[Report bugs](https://github.com/helicone/ai-gateway/issues)**: Github issues
*   💼 **[Enterprise Support](https://cal.com/team/helicone/helicone-discovery)**: Book a discovery call with our team

* * *

📄 License
----------

[](http://github.com/Helicone/ai-gateway#-license)
The Helicone AI Gateway is licensed under the [Apache License](https://github.com/Helicone/ai-gateway/blob/main/LICENSE) - see the file for details.

* * *

**Made with ❤️ by [Helicone](https://helicone.ai/).**

[Website](https://helicone.ai/) • [Docs](https://docs.helicone.ai/ai-gateway/introduction) • [Twitter](https://twitter.com/helicone_ai) • [Discord](https://discord.gg/7aSCGCGUeu)
