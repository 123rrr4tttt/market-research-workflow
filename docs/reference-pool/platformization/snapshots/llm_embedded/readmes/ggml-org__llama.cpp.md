Title: GitHub - ggml-org/llama.cpp: LLM inference in C/C++

URL Source: http://github.com/ggml-org/llama.cpp

Markdown Content:
[![Image 1: llama](https://user-images.githubusercontent.com/1991296/230134379-7181e485-c521-4d23-a0d6-f7b3b61ba524.png)](https://user-images.githubusercontent.com/1991296/230134379-7181e485-c521-4d23-a0d6-f7b3b61ba524.png)

[![Image 2: License: MIT](https://camo.githubusercontent.com/7013272bd27ece47364536a221edb554cd69683b68a46fc0ee96881174c4214c/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f6c6963656e73652d4d49542d626c75652e737667)](https://opensource.org/licenses/MIT)[![Image 3: Release](https://camo.githubusercontent.com/e6b8287fcfee35b19cb6445b354371e6c41a7a0cb476b792453247b373bc92d9/68747470733a2f2f696d672e736869656c64732e696f2f6769746875622f762f72656c656173652f67676d6c2d6f72672f6c6c616d612e637070)](https://github.com/ggml-org/llama.cpp/releases)[![Image 4: Server](https://github.com/ggml-org/llama.cpp/actions/workflows/server.yml/badge.svg)](https://github.com/ggml-org/llama.cpp/actions/workflows/server.yml)

[Manifesto](https://github.com/ggml-org/llama.cpp/discussions/205) / [ggml](https://github.com/ggml-org/ggml) / [ops](https://github.com/ggml-org/llama.cpp/blob/master/docs/ops.md)

LLM inference in C/C++

Recent API changes
------------------

[](http://github.com/ggml-org/llama.cpp#recent-api-changes)
*   [Changelog for `libllama` API](https://github.com/ggml-org/llama.cpp/issues/9289)
*   [Changelog for `llama-server` REST API](https://github.com/ggml-org/llama.cpp/issues/9291)

Hot topics
----------

[](http://github.com/ggml-org/llama.cpp#hot-topics)
*   **[guide : using the new WebUI of llama.cpp](https://github.com/ggml-org/llama.cpp/discussions/16938)**
*   [guide : running gpt-oss with llama.cpp](https://github.com/ggml-org/llama.cpp/discussions/15396)
*   [[FEEDBACK] Better packaging for llama.cpp to support downstream consumers 🤗](https://github.com/ggml-org/llama.cpp/discussions/15313)
*   Support for the `gpt-oss` model with native MXFP4 format has been added | [PR](https://github.com/ggml-org/llama.cpp/pull/15091) | [Collaboration with NVIDIA](https://blogs.nvidia.com/blog/rtx-ai-garage-openai-oss) | [Comment](https://github.com/ggml-org/llama.cpp/discussions/15095)
*   Multimodal support arrived in `llama-server`: [#12898](https://github.com/ggml-org/llama.cpp/pull/12898) | [documentation](https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md)
*   VS Code extension for FIM completions: [https://github.com/ggml-org/llama.vscode](https://github.com/ggml-org/llama.vscode)
*   Vim/Neovim plugin for FIM completions: [https://github.com/ggml-org/llama.vim](https://github.com/ggml-org/llama.vim)
*   Hugging Face Inference Endpoints now support GGUF out of the box! [#9669](https://github.com/ggml-org/llama.cpp/discussions/9669)
*   Hugging Face GGUF editor: [discussion](https://github.com/ggml-org/llama.cpp/discussions/9268) | [tool](https://huggingface.co/spaces/CISCai/gguf-editor)

* * *

Quick start
-----------

[](http://github.com/ggml-org/llama.cpp#quick-start)
Getting started with llama.cpp is straightforward. Here are several ways to install it on your machine:

*   Install `llama.cpp` using [brew, nix or winget](https://github.com/ggml-org/llama.cpp/blob/master/docs/install.md)
*   Run with Docker - see our [Docker documentation](https://github.com/ggml-org/llama.cpp/blob/master/docs/docker.md)
*   Download pre-built binaries from the [releases page](https://github.com/ggml-org/llama.cpp/releases)
*   Build from source by cloning this repository - check out [our build guide](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md)

Once installed, you'll need a model to work with. Head to the [Obtaining and quantizing models](http://github.com/ggml-org/llama.cpp#obtaining-and-quantizing-models) section to learn more.

Example command:

# Use a local model file
llama-cli -m my_model.gguf

# Or download and run a model directly from Hugging Face
llama-cli -hf ggml-org/gemma-3-1b-it-GGUF

# Launch OpenAI-compatible API server
llama-server -hf ggml-org/gemma-3-1b-it-GGUF

Description
-----------

[](http://github.com/ggml-org/llama.cpp#description)
The main goal of `llama.cpp` is to enable LLM inference with minimal setup and state-of-the-art performance on a wide range of hardware - locally and in the cloud.

*   Plain C/C++ implementation without any dependencies
*   Apple silicon is a first-class citizen - optimized via ARM NEON, Accelerate and Metal frameworks
*   AVX, AVX2, AVX512 and AMX support for x86 architectures
*   RVV, ZVFH, ZFH, ZICBOP and ZIHINTPAUSE support for RISC-V architectures
*   1.5-bit, 2-bit, 3-bit, 4-bit, 5-bit, 6-bit, and 8-bit integer quantization for faster inference and reduced memory use
*   Custom CUDA kernels for running LLMs on NVIDIA GPUs (support for AMD GPUs via HIP and Moore Threads GPUs via MUSA)
*   Vulkan and SYCL backend support
*   CPU+GPU hybrid inference to partially accelerate models larger than the total VRAM capacity

The `llama.cpp` project is the main playground for developing new features for the [ggml](https://github.com/ggml-org/ggml) library.

Models
Typically finetunes of the base models below are supported as well.

Instructions for adding support for new models: [HOWTO-add-model.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/development/HOWTO-add-model.md)

#### Text-only

[](http://github.com/ggml-org/llama.cpp#text-only)
*    LLaMA 🦙
*    LLaMA 2 🦙🦙
*    LLaMA 3 🦙🦙🦙
*   [Mistral 7B](https://huggingface.co/mistralai/Mistral-7B-v0.1)
*   [Mixtral MoE](https://huggingface.co/models?search=mistral-ai/Mixtral)
*   [DBRX](https://huggingface.co/databricks/dbrx-instruct)
*   [Jamba](https://huggingface.co/ai21labs)
*   [Falcon](https://huggingface.co/models?search=tiiuae/falcon)
*   [Chinese LLaMA / Alpaca](https://github.com/ymcui/Chinese-LLaMA-Alpaca) and [Chinese LLaMA-2 / Alpaca-2](https://github.com/ymcui/Chinese-LLaMA-Alpaca-2)
*   [Vigogne (French)](https://github.com/bofenghuang/vigogne)
*   [BERT](https://github.com/ggml-org/llama.cpp/pull/5423)
*   [Koala](https://bair.berkeley.edu/blog/2023/04/03/koala/)
*   [Baichuan 1 & 2](https://huggingface.co/models?search=baichuan-inc/Baichuan) + [derivations](https://huggingface.co/hiyouga/baichuan-7b-sft)
*   [Aquila 1 & 2](https://huggingface.co/models?search=BAAI/Aquila)
*   [Starcoder models](https://github.com/ggml-org/llama.cpp/pull/3187)
*   [Refact](https://huggingface.co/smallcloudai/Refact-1_6B-fim)
*   [MPT](https://github.com/ggml-org/llama.cpp/pull/3417)
*   [Bloom](https://github.com/ggml-org/llama.cpp/pull/3553)
*   [Yi models](https://huggingface.co/models?search=01-ai/Yi)
*   [StableLM models](https://huggingface.co/stabilityai)
*   [Deepseek models](https://huggingface.co/models?search=deepseek-ai/deepseek)
*   [Qwen models](https://huggingface.co/models?search=Qwen/Qwen)
*   [PLaMo-13B](https://github.com/ggml-org/llama.cpp/pull/3557)
*   [Phi models](https://huggingface.co/models?search=microsoft/phi)
*   [PhiMoE](https://github.com/ggml-org/llama.cpp/pull/11003)
*   [GPT-2](https://huggingface.co/gpt2)
*   [Orion 14B](https://github.com/ggml-org/llama.cpp/pull/5118)
*   [InternLM2](https://huggingface.co/models?search=internlm2)
*   [CodeShell](https://github.com/WisdomShell/codeshell)
*   [Gemma](https://ai.google.dev/gemma)
*   [Mamba](https://github.com/state-spaces/mamba)
*   [Grok-1](https://huggingface.co/keyfan/grok-1-hf)
*   [Xverse](https://huggingface.co/models?search=xverse)
*   [Command-R models](https://huggingface.co/models?search=CohereForAI/c4ai-command-r)
*   [SEA-LION](https://huggingface.co/models?search=sea-lion)
*   [GritLM-7B](https://huggingface.co/GritLM/GritLM-7B) + [GritLM-8x7B](https://huggingface.co/GritLM/GritLM-8x7B)
*   [OLMo](https://allenai.org/olmo)
*   [OLMo 2](https://allenai.org/olmo)
*   [OLMoE](https://huggingface.co/allenai/OLMoE-1B-7B-0924)
*   [Granite models](https://huggingface.co/collections/ibm-granite/granite-code-models-6624c5cec322e4c148c8b330)
*   [GPT-NeoX](https://github.com/EleutherAI/gpt-neox) + [Pythia](https://github.com/EleutherAI/pythia)
*   [Snowflake-Arctic MoE](https://huggingface.co/collections/Snowflake/arctic-66290090abe542894a5ac520)
*   [Smaug](https://huggingface.co/models?search=Smaug)
*   [Poro 34B](https://huggingface.co/LumiOpen/Poro-34B)
*   [Bitnet b1.58 models](https://huggingface.co/1bitLLM)
*   [Flan T5](https://huggingface.co/models?search=flan-t5)
*   [Open Elm models](https://huggingface.co/collections/apple/openelm-instruct-models-6619ad295d7ae9f868b759ca)
*   [ChatGLM3-6b](https://huggingface.co/THUDM/chatglm3-6b) + [ChatGLM4-9b](https://huggingface.co/THUDM/glm-4-9b) + [GLMEdge-1.5b](https://huggingface.co/THUDM/glm-edge-1.5b-chat) + [GLMEdge-4b](https://huggingface.co/THUDM/glm-edge-4b-chat)
*   [GLM-4-0414](https://huggingface.co/collections/THUDM/glm-4-0414-67f3cbcb34dd9d252707cb2e)
*   [SmolLM](https://huggingface.co/collections/HuggingFaceTB/smollm-6695016cad7167254ce15966)
*   [EXAONE-3.0-7.8B-Instruct](https://huggingface.co/LGAI-EXAONE/EXAONE-3.0-7.8B-Instruct)
*   [FalconMamba Models](https://huggingface.co/collections/tiiuae/falconmamba-7b-66b9a580324dd1598b0f6d4a)
*   [Jais](https://huggingface.co/inceptionai/jais-13b-chat)
*   [Bielik-11B-v2.3](https://huggingface.co/collections/speakleash/bielik-11b-v23-66ee813238d9b526a072408a)
*   [RWKV-7](https://huggingface.co/collections/shoumenchougou/rwkv7-gxx-gguf)
*   [RWKV-6](https://github.com/BlinkDL/RWKV-LM)
*   [QRWKV-6](https://huggingface.co/recursal/QRWKV6-32B-Instruct-Preview-v0.1)
*   [GigaChat-20B-A3B](https://huggingface.co/ai-sage/GigaChat-20B-A3B-instruct)
*   [Trillion-7B-preview](https://huggingface.co/trillionlabs/Trillion-7B-preview)
*   [Ling models](https://huggingface.co/collections/inclusionAI/ling-67c51c85b34a7ea0aba94c32)
*   [LFM2 models](https://huggingface.co/collections/LiquidAI/lfm2-686d721927015b2ad73eaa38)
*   [Hunyuan models](https://huggingface.co/collections/tencent/hunyuan-dense-model-6890632cda26b19119c9c5e7)
*   [BailingMoeV2 (Ring/Ling 2.0) models](https://huggingface.co/collections/inclusionAI/ling-v2-68bf1dd2fc34c306c1fa6f86)

#### Multimodal

[](http://github.com/ggml-org/llama.cpp#multimodal)
*   [LLaVA 1.5 models](https://huggingface.co/collections/liuhaotian/llava-15-653aac15d994e992e2677a7e), [LLaVA 1.6 models](https://huggingface.co/collections/liuhaotian/llava-16-65b9e40155f60fd046a5ccf2)
*   [BakLLaVA](https://huggingface.co/models?search=SkunkworksAI/Bakllava)
*   [Obsidian](https://huggingface.co/NousResearch/Obsidian-3B-V0.5)
*   [ShareGPT4V](https://huggingface.co/models?search=Lin-Chen/ShareGPT4V)
*   [MobileVLM 1.7B/3B models](https://huggingface.co/models?search=mobileVLM)
*   [Yi-VL](https://huggingface.co/models?search=Yi-VL)
*   [Mini CPM](https://huggingface.co/models?search=MiniCPM)
*   [Moondream](https://huggingface.co/vikhyatk/moondream2)
*   [Bunny](https://github.com/BAAI-DCAI/Bunny)
*   [GLM-EDGE](https://huggingface.co/models?search=glm-edge)
*   [Qwen2-VL](https://huggingface.co/collections/Qwen/qwen2-vl-66cee7455501d7126940800d)
*   [LFM2-VL](https://huggingface.co/collections/LiquidAI/lfm2-vl-68963bbc84a610f7638d5ffa)

Bindings
*   Python: [ddh0/easy-llama](https://github.com/ddh0/easy-llama)
*   Python: [abetlen/llama-cpp-python](https://github.com/abetlen/llama-cpp-python)
*   Go: [go-skynet/go-llama.cpp](https://github.com/go-skynet/go-llama.cpp)
*   Node.js: [withcatai/node-llama-cpp](https://github.com/withcatai/node-llama-cpp)
*   JS/TS (llama.cpp server client): [lgrammel/modelfusion](https://modelfusion.dev/integration/model-provider/llamacpp)
*   JS/TS (Programmable Prompt Engine CLI): [offline-ai/cli](https://github.com/offline-ai/cli)
*   JavaScript/Wasm (works in browser): [tangledgroup/llama-cpp-wasm](https://github.com/tangledgroup/llama-cpp-wasm)
*   Typescript/Wasm (nicer API, available on npm): [ngxson/wllama](https://github.com/ngxson/wllama)
*   Ruby: [yoshoku/llama_cpp.rb](https://github.com/yoshoku/llama_cpp.rb)
*   Rust (more features): [edgenai/llama_cpp-rs](https://github.com/edgenai/llama_cpp-rs)
*   Rust (nicer API): [mdrokz/rust-llama.cpp](https://github.com/mdrokz/rust-llama.cpp)
*   Rust (more direct bindings): [utilityai/llama-cpp-rs](https://github.com/utilityai/llama-cpp-rs)
*   Rust (automated build from crates.io): [ShelbyJenkins/llm_client](https://github.com/ShelbyJenkins/llm_client)
*   C#/.NET: [SciSharp/LLamaSharp](https://github.com/SciSharp/LLamaSharp)
*   C#/VB.NET (more features - community license): [LM-Kit.NET](https://docs.lm-kit.com/lm-kit-net/index.html)
*   Scala 3: [donderom/llm4s](https://github.com/donderom/llm4s)
*   Clojure: [phronmophobic/llama.clj](https://github.com/phronmophobic/llama.clj)
*   React Native: [mybigday/llama.rn](https://github.com/mybigday/llama.rn)
*   Java: [kherud/java-llama.cpp](https://github.com/kherud/java-llama.cpp)
*   Java: [QuasarByte/llama-cpp-jna](https://github.com/QuasarByte/llama-cpp-jna)
*   Zig: [deins/llama.cpp.zig](https://github.com/Deins/llama.cpp.zig)
*   Flutter/Dart: [netdur/llama_cpp_dart](https://github.com/netdur/llama_cpp_dart)
*   Flutter: [xuegao-tzx/Fllama](https://github.com/xuegao-tzx/Fllama)
*   PHP (API bindings and features built on top of llama.cpp): [distantmagic/resonance](https://github.com/distantmagic/resonance)[(more info)](https://github.com/ggml-org/llama.cpp/pull/6326)
*   Guile Scheme: [guile_llama_cpp](https://savannah.nongnu.org/projects/guile-llama-cpp)
*   Swift [srgtuszy/llama-cpp-swift](https://github.com/srgtuszy/llama-cpp-swift)
*   Swift [ShenghaiWang/SwiftLlama](https://github.com/ShenghaiWang/SwiftLlama)
*   Delphi [Embarcadero/llama-cpp-delphi](https://github.com/Embarcadero/llama-cpp-delphi)
*   Go (no CGo needed): [hybridgroup/yzma](https://github.com/hybridgroup/yzma)
*   Android: [llama.android](https://github.com/ggml-org/llama.cpp/blob/master/examples/llama.android)

UIs
_(to have a project listed here, it should clearly state that it depends on `llama.cpp`)_

*   [AI Sublime Text plugin](https://github.com/yaroslavyaroslav/OpenAI-sublime-text) (MIT)
*   [BonzAI App](https://apps.apple.com/us/app/bonzai-your-local-ai-agent/id6752847988) (proprietary)
*   [cztomsik/ava](https://github.com/cztomsik/ava) (MIT)
*   [Dot](https://github.com/alexpinel/Dot) (GPL)
*   [eva](https://github.com/ylsdamxssjxxdd/eva) (MIT)
*   [iohub/collama](https://github.com/iohub/coLLaMA) (Apache-2.0)
*   [janhq/jan](https://github.com/janhq/jan) (AGPL)
*   [johnbean393/Sidekick](https://github.com/johnbean393/Sidekick) (MIT)
*   [KanTV](https://github.com/zhouwg/kantv?tab=readme-ov-file) (Apache-2.0)
*   [KodiBot](https://github.com/firatkiral/kodibot) (GPL)
*   [llama.vim](https://github.com/ggml-org/llama.vim) (MIT)
*   [LARS](https://github.com/abgulati/LARS) (AGPL)
*   [Llama Assistant](https://github.com/vietanhdev/llama-assistant) (GPL)
*   [LlamaLib](https://github.com/undreamai/LlamaLib) (Apache-2.0)
*   [LLMFarm](https://github.com/guinmoon/LLMFarm?tab=readme-ov-file) (MIT)
*   [LLMUnity](https://github.com/undreamai/LLMUnity) (MIT)
*   [LMStudio](https://lmstudio.ai/) (proprietary)
*   [LocalAI](https://github.com/mudler/LocalAI) (MIT)
*   [LostRuins/koboldcpp](https://github.com/LostRuins/koboldcpp) (AGPL)
*   [MindMac](https://mindmac.app/) (proprietary)
*   [MindWorkAI/AI-Studio](https://github.com/MindWorkAI/AI-Studio) (FSL-1.1-MIT)
*   [Mobile-Artificial-Intelligence/maid](https://github.com/Mobile-Artificial-Intelligence/maid) (MIT)
*   [Mozilla-Ocho/llamafile](https://github.com/Mozilla-Ocho/llamafile) (Apache-2.0)
*   [nat/openplayground](https://github.com/nat/openplayground) (MIT)
*   [nomic-ai/gpt4all](https://github.com/nomic-ai/gpt4all) (MIT)
*   [ollama/ollama](https://github.com/ollama/ollama) (MIT)
*   [oobabooga/text-generation-webui](https://github.com/oobabooga/text-generation-webui) (AGPL)
*   [PocketPal AI](https://github.com/a-ghorbani/pocketpal-ai) (MIT)
*   [psugihara/FreeChat](https://github.com/psugihara/FreeChat) (MIT)
*   [ptsochantaris/emeltal](https://github.com/ptsochantaris/emeltal) (MIT)
*   [pythops/tenere](https://github.com/pythops/tenere) (AGPL)
*   [ramalama](https://github.com/containers/ramalama) (MIT)
*   [semperai/amica](https://github.com/semperai/amica) (MIT)
*   [withcatai/catai](https://github.com/withcatai/catai) (MIT)
*   [Autopen](https://github.com/blackhole89/autopen) (GPL)

Tools
*   [akx/ggify](https://github.com/akx/ggify) – download PyTorch models from HuggingFace Hub and convert them to GGML
*   [akx/ollama-dl](https://github.com/akx/ollama-dl) – download models from the Ollama library to be used directly with llama.cpp
*   [crashr/gppm](https://github.com/crashr/gppm) – launch llama.cpp instances utilizing NVIDIA Tesla P40 or P100 GPUs with reduced idle power consumption
*   [gpustack/gguf-parser](https://github.com/gpustack/gguf-parser-go/tree/main/cmd/gguf-parser) - review/check the GGUF file and estimate the memory usage
*   [Styled Lines](https://marketplace.unity.com/packages/tools/generative-ai/styled-lines-llama-cpp-model-292902) (proprietary licensed, async wrapper of inference part for game development in Unity3d with pre-built Mobile and Web platform wrappers and a model example)
*   [unslothai/unsloth](https://github.com/unslothai/unsloth) – 🦥 exports/saves fine-tuned and trained models to GGUF (Apache-2.0)

Infrastructure
*   [Paddler](https://github.com/intentee/paddler) - Open-source LLMOps platform for hosting and scaling AI in your own infrastructure
*   [GPUStack](https://github.com/gpustack/gpustack) - Manage GPU clusters for running LLMs
*   [llama_cpp_canister](https://github.com/onicai/llama_cpp_canister) - llama.cpp as a smart contract on the Internet Computer, using WebAssembly
*   [llama-swap](https://github.com/mostlygeek/llama-swap) - transparent proxy that adds automatic model switching with llama-server
*   [Kalavai](https://github.com/kalavai-net/kalavai-client) - Crowdsource end to end LLM deployment at any scale
*   [llmaz](https://github.com/InftyAI/llmaz) - ☸️ Easy, advanced inference platform for large language models on Kubernetes.

Games
*   [Lucy's Labyrinth](https://github.com/MorganRO8/Lucys_Labyrinth) - A simple maze game where agents controlled by an AI model will try to trick you.

Supported backends
------------------

[](http://github.com/ggml-org/llama.cpp#supported-backends)
| Backend | Target devices |
| --- | --- |
| [Metal](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md#metal-build) | Apple Silicon |
| [BLAS](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md#blas-build) | All |
| [BLIS](https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/BLIS.md) | All |
| [SYCL](https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/SYCL.md) | Intel and Nvidia GPU |
| [MUSA](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md#musa) | Moore Threads GPU |
| [CUDA](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md#cuda) | Nvidia GPU |
| [HIP](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md#hip) | AMD GPU |
| [ZenDNN](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md#zendnn) | AMD CPU |
| [Vulkan](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md#vulkan) | GPU |
| [CANN](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md#cann) | Ascend NPU |
| [OpenCL](https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/OPENCL.md) | Adreno GPU |
| [IBM zDNN](https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/zDNN.md) | IBM Z & LinuxONE |
| [WebGPU [In Progress]](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md#webgpu) | All |
| [RPC](https://github.com/ggml-org/llama.cpp/tree/master/tools/rpc) | All |
| [Hexagon [In Progress]](https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/hexagon/README.md) | Snapdragon |
| [VirtGPU](https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/VirtGPU.md) | VirtGPU APIR |

Obtaining and quantizing models
-------------------------------

[](http://github.com/ggml-org/llama.cpp#obtaining-and-quantizing-models)
The [Hugging Face](https://huggingface.co/) platform hosts a [number of LLMs](https://huggingface.co/models?library=gguf&sort=trending) compatible with `llama.cpp`:

*   [Trending](https://huggingface.co/models?library=gguf&sort=trending)
*   [LLaMA](https://huggingface.co/models?sort=trending&search=llama+gguf)

You can either manually download the GGUF file or directly use any `llama.cpp`-compatible models from [Hugging Face](https://huggingface.co/) or other model hosting sites, such as [ModelScope](https://modelscope.cn/), by using this CLI argument: `-hf <user>/<model>[:quant]`. For example:

llama-cli -hf ggml-org/gemma-3-1b-it-GGUF

By default, the CLI would download from Hugging Face, you can switch to other options with the environment variable `MODEL_ENDPOINT`. For example, you may opt to downloading model checkpoints from ModelScope or other model sharing communities by setting the environment variable, e.g. `MODEL_ENDPOINT=https://www.modelscope.cn/`.

After downloading a model, use the CLI tools to run it locally - see below.

`llama.cpp` requires the model to be stored in the [GGUF](https://github.com/ggml-org/ggml/blob/master/docs/gguf.md) file format. Models in other data formats can be converted to GGUF using the `convert_*.py` Python scripts in this repo.

The Hugging Face platform provides a variety of online tools for converting, quantizing and hosting models with `llama.cpp`:

*   Use the [GGUF-my-repo space](https://huggingface.co/spaces/ggml-org/gguf-my-repo) to convert to GGUF format and quantize model weights to smaller sizes
*   Use the [GGUF-my-LoRA space](https://huggingface.co/spaces/ggml-org/gguf-my-lora) to convert LoRA adapters to GGUF format (more info: [#10123](https://github.com/ggml-org/llama.cpp/discussions/10123))
*   Use the [GGUF-editor space](https://huggingface.co/spaces/CISCai/gguf-editor) to edit GGUF meta data in the browser (more info: [#9268](https://github.com/ggml-org/llama.cpp/discussions/9268))
*   Use the [Inference Endpoints](https://ui.endpoints.huggingface.co/) to directly host `llama.cpp` in the cloud (more info: [#9669](https://github.com/ggml-org/llama.cpp/discussions/9669))

To learn more about model quantization, [read this documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/quantize/README.md)

[`llama-cli`](https://github.com/ggml-org/llama.cpp/blob/master/tools/cli)
--------------------------------------------------------------------------

[](http://github.com/ggml-org/llama.cpp#llama-cli)
#### A CLI tool for accessing and experimenting with most of `llama.cpp`'s functionality.

[](http://github.com/ggml-org/llama.cpp#a-cli-tool-for-accessing-and-experimenting-with-most-of-llamacpps-functionality)
*   Run in conversation mode
Models with a built-in chat template will automatically activate conversation mode. If this doesn't occur, you can manually enable it by adding `-cnv` and specifying a suitable chat template with `--chat-template NAME`

llama-cli -m model.gguf

# > hi, who are you?
# Hi there! I'm your helpful assistant! I'm an AI-powered chatbot designed to assist and provide information to users like you. I'm here to help answer your questions, provide guidance, and offer support on a wide range of topics. I'm a friendly and knowledgeable AI, and I'm always happy to help with anything you need. What's on your mind, and how can I assist you today?
#
# > what is 1+1?
# Easy peasy! The answer to 1+1 is... 2!  
*   Run in conversation mode with custom chat template# use the "chatml" template (use -h to see the list of supported templates)
llama-cli -m model.gguf -cnv --chat-template chatml

# use a custom template
llama-cli -m model.gguf -cnv --in-prefix 'User: ' --reverse-prompt 'User:'  
*   Constrain the output with a custom grammar llama-cli -m model.gguf -n 256 --grammar-file grammars/json.gbnf -p 'Request: schedule a call at 8pm; Command:'

# {"appointmentTime": "8pm", "appointmentDetails": "schedule a a call"} 
The [grammars/](https://github.com/ggml-org/llama.cpp/blob/master/grammars) folder contains a handful of sample grammars. To write your own, check out the [GBNF Guide](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md).

For authoring more complex JSON grammars, check out [https://grammar.intrinsiclabs.ai/](https://grammar.intrinsiclabs.ai/) 

[`llama-server`](https://github.com/ggml-org/llama.cpp/blob/master/tools/server)
--------------------------------------------------------------------------------

[](http://github.com/ggml-org/llama.cpp#llama-server)
#### A lightweight, [OpenAI API](https://github.com/openai/openai-openapi) compatible, HTTP server for serving LLMs.

[](http://github.com/ggml-org/llama.cpp#a-lightweight-openai-api-compatible-http-server-for-serving-llms)
*   Start a local HTTP server with default configuration on port 8080 llama-server -m model.gguf --port 8080

# Basic web UI can be accessed via browser: http://localhost:8080
# Chat completion endpoint: http://localhost:8080/v1/chat/completions  
*   Support multiple-users and parallel decoding# up to 4 concurrent requests, each with 4096 max context
llama-server -m model.gguf -c 16384 -np 4  
*   Enable speculative decoding# the draft.gguf model should be a small variant of the target model.gguf
llama-server -m model.gguf -md draft.gguf  
*   Serve an embedding model# use the /embedding endpoint
llama-server -m model.gguf --embedding --pooling cls -ub 8192  
*   Serve a reranking model# use the /reranking endpoint
llama-server -m model.gguf --reranking  
*   Constrain all outputs with a grammar# custom grammar
llama-server -m model.gguf --grammar-file grammar.gbnf

# JSON
llama-server -m model.gguf --grammar-file grammars/json.gbnf  

[`llama-perplexity`](https://github.com/ggml-org/llama.cpp/blob/master/tools/perplexity)
----------------------------------------------------------------------------------------

[](http://github.com/ggml-org/llama.cpp#llama-perplexity)
#### A tool for measuring the [perplexity](https://github.com/ggml-org/llama.cpp/blob/master/tools/perplexity/README.md)[1](http://github.com/ggml-org/llama.cpp#user-content-fn-1-eebfd1d2764502c927388bb6f2429956) (and other quality metrics) of a model over a given text.

[](http://github.com/ggml-org/llama.cpp#a-tool-for-measuring-the-perplexity-1-and-other-quality-metrics-of-a-model-over-a-given-text)
*   Measure the perplexity over a text file llama-perplexity -m model.gguf -f file.txt

# [1]15.2701,[2]5.4007,[3]5.3073,[4]6.2965,[5]5.8940,[6]5.6096,[7]5.7942,[8]4.9297, ...
# Final estimate: PPL = 5.4007 +/- 0.67339  
*   Measure KL divergence# TODO  

[`llama-bench`](https://github.com/ggml-org/llama.cpp/blob/master/tools/llama-bench)
------------------------------------------------------------------------------------

[](http://github.com/ggml-org/llama.cpp#llama-bench)
#### Benchmark the performance of the inference for various parameters.

[](http://github.com/ggml-org/llama.cpp#benchmark-the-performance-of-the-inference-for-various-parameters)
*   Run default benchmark llama-bench -m model.gguf

# Output:
# | model | size | params | backend | threads | test | t/s |
# | ------------------- | ---------: | ---------: | ---------- | ------: | ------------: | -------------------: |
# | qwen2 1.5B Q4_0 | 885.97 MiB | 1.54 B | Metal,BLAS | 16 | pp512 | 5765.41 ± 20.55 |
# | qwen2 1.5B Q4_0 | 885.97 MiB | 1.54 B | Metal,BLAS | 16 | tg128 | 197.71 ± 0.81 |
#
# build: 3e0ba0e60 (4229)  

[`llama-simple`](https://github.com/ggml-org/llama.cpp/blob/master/examples/simple)
-----------------------------------------------------------------------------------

[](http://github.com/ggml-org/llama.cpp#llama-simple)
#### A minimal example for implementing apps with `llama.cpp`. Useful for developers.

[](http://github.com/ggml-org/llama.cpp#a-minimal-example-for-implementing-apps-with-llamacpp-useful-for-developers)
*   Basic text completion llama-simple -m model.gguf

# Hello my name is Kaitlyn and I am a 16 year old girl. I am a junior in high school and I am currently taking a class called "The Art of  

Contributing
------------

[](http://github.com/ggml-org/llama.cpp#contributing)
*   Contributors can open PRs
*   Collaborators will be invited based on contributions
*   Maintainers can push to branches in the `llama.cpp` repo and merge PRs into the `master` branch
*   Any help with managing issues, PRs and projects is very appreciated!
*   See [good first issues](https://github.com/ggml-org/llama.cpp/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) for tasks suitable for first contributions
*   Read the [CONTRIBUTING.md](https://github.com/ggml-org/llama.cpp/blob/master/CONTRIBUTING.md) for more information
*   Make sure to read this: [Inference at the edge](https://github.com/ggml-org/llama.cpp/discussions/205)
*   A bit of backstory for those who are interested: [Changelog podcast](https://changelog.com/podcast/532)

Other documentation
-------------------

[](http://github.com/ggml-org/llama.cpp#other-documentation)
*   [cli](https://github.com/ggml-org/llama.cpp/blob/master/tools/cli/README.md)
*   [completion](https://github.com/ggml-org/llama.cpp/blob/master/tools/completion/README.md)
*   [server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
*   [GBNF grammars](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)

#### Development documentation

[](http://github.com/ggml-org/llama.cpp#development-documentation)
*   [How to build](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md)
*   [Running on Docker](https://github.com/ggml-org/llama.cpp/blob/master/docs/docker.md)
*   [Build on Android](https://github.com/ggml-org/llama.cpp/blob/master/docs/android.md)
*   [Performance troubleshooting](https://github.com/ggml-org/llama.cpp/blob/master/docs/development/token_generation_performance_tips.md)
*   [GGML tips & tricks](https://github.com/ggml-org/llama.cpp/wiki/GGML-Tips-&-Tricks)

#### Seminal papers and background on the models

[](http://github.com/ggml-org/llama.cpp#seminal-papers-and-background-on-the-models)
If your issue is with model generation quality, then please at least scan the following links and papers to understand the limitations of LLaMA models. This is especially important when choosing an appropriate model size and appreciating both the significant and subtle differences between LLaMA models and ChatGPT:

*   LLaMA: 
    *   [Introducing LLaMA: A foundational, 65-billion-parameter large language model](https://ai.facebook.com/blog/large-language-model-llama-meta-ai/)
    *   [LLaMA: Open and Efficient Foundation Language Models](https://arxiv.org/abs/2302.13971)

*   GPT-3 
    *   [Language Models are Few-Shot Learners](https://arxiv.org/abs/2005.14165)

*   GPT-3.5 / InstructGPT / ChatGPT: 
    *   [Aligning language models to follow instructions](https://openai.com/research/instruction-following)
    *   [Training language models to follow instructions with human feedback](https://arxiv.org/abs/2203.02155)

XCFramework
-----------

[](http://github.com/ggml-org/llama.cpp#xcframework)
The XCFramework is a precompiled version of the library for iOS, visionOS, tvOS, and macOS. It can be used in Swift projects without the need to compile the library from source. For example:

// swift-tools-version: 5.10
// The swift-tools-version declares the minimum version of Swift required to build this package.

import PackageDescription

let package = Package(
    name: "MyLlamaPackage",
    targets: [
        .executableTarget(
            name: "MyLlamaPackage",
            dependencies: [
                "LlamaFramework"
            ]),
        .binaryTarget(
            name: "LlamaFramework",
            url: "https://github.com/ggml-org/llama.cpp/releases/download/b5046/llama-b5046-xcframework.zip",
            checksum: "c19be78b5f00d8d29a25da41042cb7afa094cbf6280a225abe614b03b20029ab"
        )
    ]
)

The above example is using an intermediate build `b5046` of the library. This can be modified to use a different version by changing the URL and checksum.

Completions
-----------

[](http://github.com/ggml-org/llama.cpp#completions)
Command-line completion is available for some environments.

#### Bash Completion

[](http://github.com/ggml-org/llama.cpp#bash-completion)

$ build/bin/llama-cli --completion-bash > ~/.llama-completion.bash
$ source ~/.llama-completion.bash

Optionally this can be added to your `.bashrc` or `.bash_profile` to load it automatically. For example:

$ echo "source ~/.llama-completion.bash" >> ~/.bashrc

Dependencies
------------

[](http://github.com/ggml-org/llama.cpp#dependencies)
*   [yhirose/cpp-httplib](https://github.com/yhirose/cpp-httplib) - Single-header HTTP server, used by `llama-server` - MIT license
*   [stb-image](https://github.com/nothings/stb) - Single-header image format decoder, used by multimodal subsystem - Public domain
*   [nlohmann/json](https://github.com/nlohmann/json) - Single-header JSON library, used by various tools/examples - MIT License
*   [miniaudio.h](https://github.com/mackron/miniaudio) - Single-header audio format decoder, used by multimodal subsystem - Public domain
*   [subprocess.h](https://github.com/sheredom/subprocess.h) - Single-header process launching solution for C and C++ - Public domain

Footnotes
---------

1.   [https://huggingface.co/docs/transformers/perplexity](https://huggingface.co/docs/transformers/perplexity)[↩](http://github.com/ggml-org/llama.cpp#user-content-fnref-1-eebfd1d2764502c927388bb6f2429956)
