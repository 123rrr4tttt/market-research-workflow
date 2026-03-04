Title: GitHub - confident-ai/deepeval: The LLM Evaluation Framework

URL Source: http://github.com/confident-ai/deepeval

Markdown Content:
[![Image 1: DeepEval Logo](https://github.com/confident-ai/deepeval/raw/main/docs/static/img/deepeval.png)](https://github.com/confident-ai/deepeval/blob/main/docs/static/img/deepeval.png)

[![Image 2: confident-ai%2Fdeepeval | Trendshift](https://camo.githubusercontent.com/869fe22699d6b9bde209abf203a86264e36b7e8f4d09923f7c88da2f4c877cf2/68747470733a2f2f7472656e6473686966742e696f2f6170692f62616467652f7265706f7369746f726965732f35393137)](https://trendshift.io/repositories/5917)

[![Image 3: discord-invite](https://camo.githubusercontent.com/d591d9b44265c26fc3c0b6fa4a73fd55e8519500d4192e9e6c3a11291f62a2cb/68747470733a2f2f646362616467652e76657263656c2e6170702f6170692f7365727665722f335345797670677532663f7374796c653d666c6174)](https://discord.gg/3SEyvpgu2f)

[![Image 4: GitHub release](https://camo.githubusercontent.com/ee6a15a761673594570c0059d73027b11bf60967ed14adf9cd01a180ff1ed7a6/68747470733a2f2f696d672e736869656c64732e696f2f6769746875622f72656c656173652f636f6e666964656e742d61692f646565706576616c2e7376673f636f6c6f723d76696f6c6574)](https://github.com/confident-ai/deepeval/releases)[![Image 5: Try Quickstart in Colab](https://camo.githubusercontent.com/eff96fda6b2e0fff8cdf2978f89d61aa434bb98c00453ae23dd0aab8d1451633/68747470733a2f2f636f6c61622e72657365617263682e676f6f676c652e636f6d2f6173736574732f636f6c61622d62616467652e737667)](https://colab.research.google.com/drive/1PPxYEBa6eu__LquGoFFJZkhYgWVYE6kh?usp=sharing)[![Image 6: License](https://camo.githubusercontent.com/4e2e968c2e83486f457aab65a06a2370ce8ae011cb5e2219f8dac0c0223060de/68747470733a2f2f696d672e736869656c64732e696f2f6769746875622f6c6963656e73652f636f6e666964656e742d61692f646565706576616c2e7376673f636f6c6f723d79656c6c6f77)](https://github.com/confident-ai/deepeval/blob/master/LICENSE.md)[![Image 7: Twitter Follow](https://camo.githubusercontent.com/a0cceabe8b1536b825113067fe5072bda198758a7d386b1440540d5f437f928d/68747470733a2f2f696d672e736869656c64732e696f2f747769747465722f666f6c6c6f772f646565706576616c3f7374796c653d736f6369616c266c6f676f3d78)](https://x.com/deepeval)

[Deutsch](https://www.readme-i18n.com/confident-ai/deepeval?lang=de) | [Español](https://www.readme-i18n.com/confident-ai/deepeval?lang=es) | [français](https://www.readme-i18n.com/confident-ai/deepeval?lang=fr) | [日本語](https://www.readme-i18n.com/confident-ai/deepeval?lang=ja) | [한국어](https://www.readme-i18n.com/confident-ai/deepeval?lang=ko) | [Português](https://www.readme-i18n.com/confident-ai/deepeval?lang=pt) | [Русский](https://www.readme-i18n.com/confident-ai/deepeval?lang=ru) | [中文](https://www.readme-i18n.com/confident-ai/deepeval?lang=zh)

**DeepEval** is a simple-to-use, open-source LLM evaluation framework, for evaluating and testing large-language model systems. It is similar to Pytest but specialized for unit testing LLM outputs. DeepEval incorporates the latest research to evaluate LLM outputs based on metrics such as G-Eval, task completion, answer relevancy, hallucination, etc., which uses LLM-as-a-judge and other NLP models that run **locally on your machine** for evaluation.

Whether your LLM applications are AI agents, RAG pipelines, or chatbots, implemented via LangChain or OpenAI, DeepEval has you covered. With it, you can easily determine the optimal models, prompts, and architecture to improve your RAG pipeline, agentic workflows, prevent prompt drifting, or even transition from OpenAI to hosting your own Deepseek R1 with confidence.

Important

Need a place for your DeepEval testing data to live 🏡❤️? [Sign up to the DeepEval platform](https://confident-ai.com/?utm_source=GitHub) to compare iterations of your LLM app, generate & share testing reports, and more.

[![Image 8: Demo GIF](https://github.com/confident-ai/deepeval/raw/main/assets/demo.gif)](https://github.com/confident-ai/deepeval/blob/main/assets/demo.gif)

> Want to talk LLM evaluation, need help picking metrics, or just to say hi? [Come join our discord.](https://discord.com/invite/3SEyvpgu2f)

🔥 Metrics and Features
-----------------------

[](http://github.com/confident-ai/deepeval#-metrics-and-features)
> 🥳 You can now share DeepEval's test results on the cloud directly on [Confident AI](https://confident-ai.com/?utm_source=GitHub)

*   Supports both end-to-end and component-level LLM evaluation.
*   Large variety of ready-to-use LLM evaluation metrics (all with explanations) powered by **ANY** LLM of your choice, statistical methods, or NLP models that run **locally on your machine**: 
    *   G-Eval
    *   DAG ([deep acyclic graph](https://deepeval.com/docs/metrics-dag))
    *   **RAG metrics:**
        *   Answer Relevancy
        *   Faithfulness
        *   Contextual Recall
        *   Contextual Precision
        *   Contextual Relevancy
        *   RAGAS

    *   **Agentic metrics:**
        *   Task Completion
        *   Tool Correctness

    *   **Others:**
        *   Hallucination
        *   Summarization
        *   Bias
        *   Toxicity

    *   **Conversational metrics:**
        *   Knowledge Retention
        *   Conversation Completeness
        *   Conversation Relevancy
        *   Role Adherence

    *   etc.

*   Build your own custom metrics that are automatically integrated with DeepEval's ecosystem.
*   Generate synthetic datasets for evaluation.
*   Integrates seamlessly with **ANY** CI/CD environment.
*   [Red team your LLM application](https://deepeval.com/docs/red-teaming-introduction) for 40+ safety vulnerabilities in a few lines of code, including: 
    *   Toxicity
    *   Bias
    *   SQL Injection
    *   etc., using advanced 10+ attack enhancement strategies such as prompt injections.

*   Easily benchmark **ANY** LLM on popular LLM benchmarks in [under 10 lines of code.](https://deepeval.com/docs/benchmarks-introduction?utm_source=GitHub), which includes: 
    *   MMLU
    *   HellaSwag
    *   DROP
    *   BIG-Bench Hard
    *   TruthfulQA
    *   HumanEval
    *   GSM8K

*   [100% integrated with Confident AI](https://confident-ai.com/?utm_source=GitHub) for the full evaluation & observability lifecycle: 
    *   Curate/annotate evaluation datasets on the cloud
    *   Benchmark LLM app using dataset, and compare with previous iterations to experiment which models/prompts works best
    *   Fine-tune metrics for custom results
    *   Debug evaluation results via LLM traces
    *   Monitor & evaluate LLM responses in product to improve datasets with real-world data
    *   Repeat until perfection

Note

DeepEval is available on Confident AI, an LLM evals platform for AI observability and quality. Create an account [here.](https://app.confident-ai.com/?utm_source=GitHub)

🔌 Integrations
---------------

[](http://github.com/confident-ai/deepeval#-integrations)
*   🦄 LlamaIndex, to [**unit test RAG applications in CI/CD**](https://www.deepeval.com/integrations/frameworks/llamaindex?utm_source=GitHub)
*   🤗 Hugging Face, to [**enable real-time evaluations during LLM fine-tuning**](https://www.deepeval.com/integrations/frameworks/huggingface?utm_source=GitHub)

🚀 QuickStart
-------------

[](http://github.com/confident-ai/deepeval#-quickstart)
Let's pretend your LLM application is a RAG based customer support chatbot; here's how DeepEval can help test what you've built.

Installation
------------

[](http://github.com/confident-ai/deepeval#installation)
Deepeval works with **Python>=3.9+**.

```
pip install -U deepeval
```

Create an account (highly recommended)
--------------------------------------

[](http://github.com/confident-ai/deepeval#create-an-account-highly-recommended)
Using the `deepeval` platform will allow you to generate sharable testing reports on the cloud. It is free, takes no additional code to setup, and we highly recommend giving it a try.

To login, run:

```
deepeval login
```

Follow the instructions in the CLI to create an account, copy your API key, and paste it into the CLI. All test cases will automatically be logged (find more information on data privacy [here](https://deepeval.com/docs/data-privacy?utm_source=GitHub)).

Writing your first test case
----------------------------

[](http://github.com/confident-ai/deepeval#writing-your-first-test-case)
Create a test file:

touch test_chatbot.py

Open `test_chatbot.py` and write your first test case to run an **end-to-end** evaluation using DeepEval, which treats your LLM app as a black-box:

import pytest
from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

def test_case():
    correctness_metric = GEval(
        name="Correctness",
        criteria="Determine if the 'actual output' is correct based on the 'expected output'.",
        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT],
        threshold=0.5
    )
    test_case = LLMTestCase(
        input="What if these shoes don't fit?",
        # Replace this with the actual output from your LLM application
        actual_output="You have 30 days to get a full refund at no extra cost.",
        expected_output="We offer a 30-day full refund at no extra costs.",
        retrieval_context=["All customers are eligible for a 30 day full refund at no extra costs."]
    )
    assert_test(test_case, [correctness_metric])

Set your `OPENAI_API_KEY` as an environment variable (you can also evaluate using your own custom model, for more details visit [this part of our docs](https://deepeval.com/docs/metrics-introduction#using-a-custom-llm?utm_source=GitHub)):

```
export OPENAI_API_KEY="..."
```

And finally, run `test_chatbot.py` in the CLI:

```
deepeval test run test_chatbot.py
```

**Congratulations! Your test case should have passed ✅** Let's breakdown what happened.

*   The variable `input` mimics a user input, and `actual_output` is a placeholder for what your application's supposed to output based on this input.
*   The variable `expected_output` represents the ideal answer for a given `input`, and [`GEval`](https://deepeval.com/docs/metrics-llm-evals) is a research-backed metric provided by `deepeval` for you to evaluate your LLM output's on any custom with human-like accuracy.
*   In this example, the metric `criteria` is correctness of the `actual_output` based on the provided `expected_output`.
*   All metric scores range from 0 - 1, which the `threshold=0.5` threshold ultimately determines if your test have passed or not.

[Read our documentation](https://deepeval.com/docs/getting-started?utm_source=GitHub) for more information on more options to run end-to-end evaluation, how to use additional metrics, create your own custom metrics, and tutorials on how to integrate with other tools like LangChain and LlamaIndex.

Evaluating Nested Components
----------------------------

[](http://github.com/confident-ai/deepeval#evaluating-nested-components)
If you wish to evaluate individual components within your LLM app, you need to run **component-level** evals - a powerful way to evaluate any component within an LLM system.

Simply trace "components" such as LLM calls, retrievers, tool calls, and agents within your LLM application using the `@observe` decorator to apply metrics on a component-level. Tracing with `deepeval` is non-instrusive (learn more [here](https://deepeval.com/docs/evaluation-llm-tracing#dont-be-worried-about-tracing)) and helps you avoid rewriting your codebase just for evals:

from deepeval.tracing import observe, update_current_span
from deepeval.test_case import LLMTestCase
from deepeval.dataset import Golden
from deepeval.metrics import GEval
from deepeval import evaluate

correctness = GEval(name="Correctness", criteria="Determine if the 'actual output' is correct based on the 'expected output'.", evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT])

@observe(metrics=[correctness])
def inner_component():
    # Component can be anything from an LLM call, retrieval, agent, tool use, etc.
    update_current_span(test_case=LLMTestCase(input="...", actual_output="..."))
    return

@observe
def llm_app(input: str):
    inner_component()
    return

evaluate(observed_callback=llm_app, goldens=[Golden(input="Hi!")])

You can learn everything about component-level evaluations [here.](https://www.deepeval.com/docs/evaluation-component-level-llm-evals)

Evaluating Without Pytest Integration
-------------------------------------

[](http://github.com/confident-ai/deepeval#evaluating-without-pytest-integration)
Alternatively, you can evaluate without Pytest, which is more suited for a notebook environment.

from deepeval import evaluate
from deepeval.metrics import AnswerRelevancyMetric
from deepeval.test_case import LLMTestCase

answer_relevancy_metric = AnswerRelevancyMetric(threshold=0.7)
test_case = LLMTestCase(
    input="What if these shoes don't fit?",
    # Replace this with the actual output from your LLM application
    actual_output="We offer a 30-day full refund at no extra costs.",
    retrieval_context=["All customers are eligible for a 30 day full refund at no extra costs."]
)
evaluate([test_case], [answer_relevancy_metric])

Using Standalone Metrics
------------------------

[](http://github.com/confident-ai/deepeval#using-standalone-metrics)
DeepEval is extremely modular, making it easy for anyone to use any of our metrics. Continuing from the previous example:

from deepeval.metrics import AnswerRelevancyMetric
from deepeval.test_case import LLMTestCase

answer_relevancy_metric = AnswerRelevancyMetric(threshold=0.7)
test_case = LLMTestCase(
    input="What if these shoes don't fit?",
    # Replace this with the actual output from your LLM application
    actual_output="We offer a 30-day full refund at no extra costs.",
    retrieval_context=["All customers are eligible for a 30 day full refund at no extra costs."]
)

answer_relevancy_metric.measure(test_case)
print(answer_relevancy_metric.score)
# All metrics also offer an explanation
print(answer_relevancy_metric.reason)

Note that some metrics are for RAG pipelines, while others are for fine-tuning. Make sure to use our docs to pick the right one for your use case.

Evaluating a Dataset / Test Cases in Bulk
-----------------------------------------

[](http://github.com/confident-ai/deepeval#evaluating-a-dataset--test-cases-in-bulk)
In DeepEval, a dataset is simply a collection of test cases. Here is how you can evaluate these in bulk:

import pytest
from deepeval import assert_test
from deepeval.dataset import EvaluationDataset, Golden
from deepeval.metrics import AnswerRelevancyMetric
from deepeval.test_case import LLMTestCase

dataset = EvaluationDataset(goldens=[Golden(input="What's the weather like today?")])

for golden in dataset.goldens:
    test_case = LLMTestCase(
        input=golden.input,
        actual_output=your_llm_app(golden.input)
    )
    dataset.add_test_case(test_case)

@pytest.mark.parametrize(
 "test_case",
 dataset.test_cases,
)
def test_customer_chatbot(test_case: LLMTestCase):
    answer_relevancy_metric = AnswerRelevancyMetric(threshold=0.5)
    assert_test(test_case, [answer_relevancy_metric])

# Run this in the CLI, you can also add an optional -n flag to run tests in parallel
deepeval test run test_<filename>.py -n 4

Alternatively, although we recommend using `deepeval test run`, you can evaluate a dataset/test cases without using our Pytest integration:

from deepeval import evaluate
...

evaluate(dataset, [answer_relevancy_metric])
# or
dataset.evaluate([answer_relevancy_metric])

A Note on Env Variables (.env / .env.local)
-------------------------------------------

[](http://github.com/confident-ai/deepeval#a-note-on-env-variables-env--envlocal)
DeepEval auto-loads `.env.local` then `.env` from the current working directory **at import time**. **Precedence:** process env ->`.env.local` ->`.env`. Opt out with `DEEPEVAL_DISABLE_DOTENV=1`.

cp .env.example .env.local
# then edit .env.local (ignored by git)

DeepEval With Confident AI
--------------------------

[](http://github.com/confident-ai/deepeval#deepeval-with-confident-ai)
DeepEval is available on [Confident AI](https://confident-ai.com/?utm_source=Github), an evals & observability platform that allows you to:

1.   Curate/annotate evaluation datasets on the cloud
2.   Benchmark LLM app using dataset, and compare with previous iterations to experiment which models/prompts works best
3.   Fine-tune metrics for custom results
4.   Debug evaluation results via LLM traces
5.   Monitor & evaluate LLM responses in product to improve datasets with real-world data
6.   Repeat until perfection

Everything on Confident AI, including how to use Confident is available [here](https://www.confident-ai.com/docs?utm_source=GitHub).

To begin, login from the CLI:

deepeval login

Follow the instructions to log in, create your account, and paste your API key into the CLI.

Now, run your test file again:

deepeval test run test_chatbot.py

You should see a link displayed in the CLI once the test has finished running. Paste it into your browser to view the results!

[![Image 9: Demo GIF](https://github.com/confident-ai/deepeval/raw/main/assets/demo.gif)](https://github.com/confident-ai/deepeval/blob/main/assets/demo.gif)

Configuration
-------------

[](http://github.com/confident-ai/deepeval#configuration)
### Environment variables via .env files

[](http://github.com/confident-ai/deepeval#environment-variables-via-env-files)
Using `.env.local` or `.env` is optional. If they are missing, DeepEval uses your existing environment variables. When present, dotenv environment variables are auto-loaded at import time (unless you set `DEEPEVAL_DISABLE_DOTENV=1`).

**Precedence:** process env ->`.env.local` ->`.env`

cp .env.example .env.local
# then edit .env.local (ignored by git)

Contributing
------------

[](http://github.com/confident-ai/deepeval#contributing)
Please read [CONTRIBUTING.md](https://github.com/confident-ai/deepeval/blob/main/CONTRIBUTING.md) for details on our code of conduct, and the process for submitting pull requests to us.

Roadmap
-------

[](http://github.com/confident-ai/deepeval#roadmap)
Features:

*    Integration with Confident AI
*    Implement G-Eval
*    Implement RAG metrics
*    Implement Conversational metrics
*    Evaluation Dataset Creation
*    Red-Teaming
*    DAG custom metrics
*    Guardrails

Authors
-------

[](http://github.com/confident-ai/deepeval#authors)
Built by the founders of Confident AI. Contact [jeffreyip@confident-ai.com](mailto:jeffreyip@confident-ai.com) for all enquiries.

License
-------

[](http://github.com/confident-ai/deepeval#license)
DeepEval is licensed under Apache 2.0 - see the [LICENSE.md](https://github.com/confident-ai/deepeval/blob/main/LICENSE.md) file for details.
