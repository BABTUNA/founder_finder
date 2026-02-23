# Browser-Use — Reference & Best Practices

> **Source**: [docs.browser-use.com](https://docs.browser-use.com/introduction)
>
> Browser-Use is an open-source Python library that lets you automate browser tasks with plain-text instructions powered by LLMs.

---

## Table of Contents

1. [Installation](#1-installation)
2. [Two Agent Types — Agent vs CodeAgent](#2-two-agent-types)
3. [Supported LLM Models](#3-supported-llm-models)
4. [Agent Configuration Reference](#4-agent-configuration-reference)
5. [CodeAgent Reference](#5-codeagent-reference)
6. [Browser Configuration Reference](#6-browser-configuration-reference)
7. [Task Prompt Best Practices](#7-task-prompt-best-practices)
8. [Going to Production](#8-going-to-production)
9. [Common Patterns & Examples](#9-common-patterns--examples)

---

## 1. Installation

```bash
# Create and activate a venv
pip install uv
uv venv --python 3.12
.venv\Scripts\Activate          # Windows PowerShell
# source .venv/bin/activate     # macOS / Linux

# Install browser-use + playwright browsers
uv pip install browser-use
uvx browser-use install
```

Create a `.env` file with your API key:

```env
BROWSER_USE_API_KEY=your-key      # Get free credits at https://cloud.browser-use.com/new-api-key

# Or use your own model keys directly:
# ANTHROPIC_API_KEY=...
# OPENAI_API_KEY=...
# GOOGLE_API_KEY=...
```

---

## 2. Two Agent Types

### `Agent` — Natural-Language (Default)

The standard agent interprets your task, takes browser actions step-by-step, and returns a result. Best for:

- **One-off tasks** — "find the top post on Hacker News"
- **Interactive workflows** — login, fill forms, navigate multi-page flows
- **Quick prototyping** — get results without writing any extraction logic

```python
import asyncio
from browser_use import Agent, ChatBrowserUse
from dotenv import load_dotenv

load_dotenv()

async def main():
    agent = Agent(
        task="Find the #1 post on Show HN",
        llm=ChatBrowserUse(),
    )
    await agent.run()

asyncio.run(main())
```

### `CodeAgent` — Code Execution Agent

Writes and executes Python code cells (like a Jupyter notebook) to interact with the browser. Best for:

- **Data extraction at scale** (100s–1000s of items)
- **Repetitive interactions** where functions can be reused across pages
- **Tasks requiring data processing** — pandas, CSV writing, etc.
- **Deterministic workflows** you want to export and re-run later

```python
import asyncio
from browser_use.code_use import CodeAgent
from dotenv import load_dotenv

load_dotenv()

async def main():
    agent = CodeAgent(
        task="Extract all products from example.com and save to products.csv",
        max_steps=100,
    )
    session = await agent.run()
    print(f"Session has {len(session.cells)} cells.")
    await agent.close()

asyncio.run(main())
```

> [!IMPORTANT]
> `CodeAgent` **requires** `BROWSER_USE_API_KEY` (cloud model). It uses `ChatBrowserUse` internally.

#### CodeAgent Available Tools (inside generated code)

| Tool | Description |
|---|---|
| `navigate(url)` | Navigate to a URL |
| `click(index)` | Click an element by its index on the page |
| `input(index, text)` | Type text into an input field |
| `scroll(down, pages)` | Scroll the page |
| `upload_file(path)` | Upload a file |
| `evaluate(code, variables={})` | Execute JavaScript and return results |
| `done(text, success, files_to_display=[])` | Mark the task as complete |

#### CodeAgent Available Libraries

`pandas`, `numpy`, `requests`, `BeautifulSoup`, `csv`, `json`, `openpyxl`, `matplotlib`, `tabulate`, `datetime`, `re`, plus anything installed in the environment.

#### Exporting Sessions

```python
from browser_use.code_use.notebook_export import export_to_ipynb, session_to_python_script

await agent.run()

# Jupyter notebook
export_to_ipynb(agent, "my_automation.ipynb")

# Python script
script = session_to_python_script(agent)
with open("my_automation.py", "w") as f:
    f.write(script)
```

---

## 3. Supported LLM Models

### Browser-Use Native (Recommended for CodeAgent)

```python
from browser_use import ChatBrowserUse
llm = ChatBrowserUse()             # "bu-latest" (default)
llm = ChatBrowserUse(model="bu-2-0")  # Premium model
```
Requires `BROWSER_USE_API_KEY`.

### Anthropic (Claude)

```python
from browser_use import ChatAnthropic
llm = ChatAnthropic(model="claude-sonnet-4-0")
```
Requires `ANTHROPIC_API_KEY`.

### OpenAI

```python
from browser_use import ChatOpenAI
llm = ChatOpenAI(model="o3")
```
Requires `OPENAI_API_KEY`.

### Google Gemini

```python
from browser_use import ChatGoogle
llm = ChatGoogle(model="gemini-flash-latest")
```
Requires `GOOGLE_API_KEY`.

### Others

Azure OpenAI, AWS Bedrock, Groq, Ollama, Qwen, and any LangChain-compatible model are also supported. See [Supported Models docs](https://docs.browser-use.com/supported-models).

---

## 4. Agent Configuration Reference

### Core Settings

| Parameter | Default | Description |
|---|---|---|
| `task` | *required* | Plain-text task description |
| `llm` | *required* | LLM model instance |
| `browser` | `None` | `Browser()` instance with custom settings |
| `tools` | built-in | Registry of tools the agent can call |
| `output_model_schema` | `None` | Pydantic model for structured output |
| `skills` / `skill_ids` | `None` | Cloud skill IDs to load (requires API key) |

### Vision & Processing

| Parameter | Default | Description |
|---|---|---|
| `use_vision` | `"auto"` | `"auto"` / `True` / `False` — controls screenshot usage |
| `vision_detail_level` | `"auto"` | `"low"` / `"high"` / `"auto"` |
| `page_extraction_llm` | same as `llm` | Cheaper/faster LLM for page content extraction |

### Actions & Behavior

| Parameter | Default | Description |
|---|---|---|
| `max_actions_per_step` | `4` | Max actions per LLM step (e.g. fill 4 form fields at once) |
| `max_failures` | `3` | Max retries for steps with errors |
| `initial_actions` | `None` | Actions to run before the main task (no LLM needed) |
| `use_thinking` | `True` | Enable internal reasoning steps |
| `flash_mode` | `False` | Fast mode — skips evaluation/thinking, uses memory only |
| `directly_open_url` | `True` | Auto-open URLs detected in the task |

### Resilience

| Parameter | Default | Description |
|---|---|---|
| `fallback_llm` | `None` | Backup LLM used after primary exhausts retries (429/401/500 errors) |
| `final_response_after_failure` | `True` | Attempt one final model call after `max_failures` |

### System Messages

| Parameter | Description |
|---|---|
| `override_system_message` | Completely replace the default system prompt |
| `extend_system_message` | Append additional instructions to the system prompt |

### Performance & Limits

| Parameter | Default | Description |
|---|---|---|
| `max_history_items` | `None` (all) | Max recent steps kept in LLM memory |
| `llm_timeout` | `90` s | Timeout for LLM calls |
| `step_timeout` | `120` s | Timeout for each step |

### File & Data

| Parameter | Description |
|---|---|
| `save_conversation_path` | Path to save full conversation history |
| `available_file_paths` | File paths the agent can access |
| `sensitive_data` | Dict of sensitive values to handle carefully |
| `generate_gif` | `False` — set `True` or a path to generate action GIFs |

---

## 5. CodeAgent Reference

```python
from browser_use.code_use import CodeAgent

agent = CodeAgent(
    task="...",          # Detailed task description
    max_steps=150,       # Max code-cell executions (default varies)
)
session = await agent.run()
await agent.close()
```

Key differences from `Agent`:

| Feature | Agent | CodeAgent |
|---|---|---|
| How it works | LLM outputs browser actions | LLM writes Python code cells |
| Best for | Interactive tasks, one-offs | Data extraction at scale |
| Speed for one-offs | Faster | Slightly slower |
| Reusability | Not easily replayable | Export to `.py` / `.ipynb` |
| Libraries | N/A | pandas, requests, etc. |
| LLM provider | Any supported model | `BROWSER_USE_API_KEY` required |

---

## 6. Browser Configuration Reference

```python
from browser_use import Browser

browser = Browser(
    headless=False,
    window_size={"width": 1920, "height": 1080},
)

agent = Agent(task="...", llm=llm, browser=browser)
```

### Key Parameters

| Parameter | Default | Description |
|---|---|---|
| `headless` | `None` (auto) | `True` = no UI, `False` = visible browser |
| `cdp_url` | `None` | Connect to existing browser via CDP |
| `window_size` | — | `{"width": W, "height": H}` |
| `viewport` | — | Content area size |
| `keep_alive` | `None` | Keep browser open after agent finishes |
| `allowed_domains` | `None` | Restrict navigation (e.g. `["*.google.com"]`) |
| `prohibited_domains` | `None` | Block domains |

### User Data & Profiles

| Parameter | Default | Description |
|---|---|---|
| `user_data_dir` | auto temp | Browser profile directory; `None` = incognito |
| `profile_directory` | `"Default"` | Chrome profile name |
| `storage_state` | `None` | Cookies/localStorage (file path or dict) |

### Network & Security

| Parameter | Description |
|---|---|
| `proxy` | `ProxySettings(server=..., username=..., password=...)` |
| `permissions` | Default: `['clipboardReadWrite', 'notifications']` |

### Browser Launch

| Parameter | Description |
|---|---|
| `executable_path` | Custom browser binary path |
| `channel` | `"chromium"` / `"chrome"` / `"chrome-beta"` / `"msedge"` |
| `args` | Extra CLI args: `["--disable-gpu"]` |
| `devtools` | `False` — auto-open DevTools (requires `headless=False`) |

### Timing & Performance

| Parameter | Default | Description |
|---|---|---|
| `minimum_wait_page_load_time` | `0.25` s | Min wait before capturing page state |
| `wait_for_network_idle_page_load_time` | `0.5` s | Wait for network idle |
| `wait_between_actions` | `0.5` s | Delay between agent actions |

---

## 7. Task Prompt Best Practices

### General Tips

1. **Be specific and step-by-step** — Break complex tasks into numbered phases.
2. **Include the target URL** in the task string — the agent will auto-navigate to it.
3. **Specify expected output format** — "Return JSON with keys: …" or "Save to CSV with columns: …"
4. **Set a reasonable `max_steps`** — Too low and the agent can't finish; too high and you waste tokens on failures.
5. **Use `extend_system_message`** to add domain-specific knowledge the agent might not have.

### For Data Extraction (CodeAgent)

- Describe the **exact CSV columns** and their order.
- Tell the agent to use **JavaScript evaluation** (`evaluate(...)`) for efficient bulk extraction.
- Mention **infinite scroll** behavior if the target page uses it.
- Instruct the agent to **skip failed pages** rather than retrying forever.
- End with a `done(...)` call containing a summary.

### For Interactive Tasks (Agent)

- Mention what **success looks like** — "You're done when you see the confirmation page."
- Use `sensitive_data` for passwords/tokens instead of putting them in the task string.
- Set `allowed_domains` on the browser to prevent navigation to unrelated sites.

---

## 8. Going to Production

### Cloud Sandbox (`@sandbox`)

```python
from browser_use import Browser, sandbox, ChatBrowserUse
from browser_use.agent.service import Agent

@sandbox()
async def my_task(browser: Browser):
    agent = Agent(
        task="Find the top HN post",
        browser=browser,
        llm=ChatBrowserUse(),
    )
    await agent.run()

asyncio.run(my_task())
```

### With Proxies

```python
@sandbox(cloud_proxy_country_code="us")
async def stealth_task(browser: Browser):
    ...
```

### With Authenticated Profiles

Sync local cookies to the cloud, then use the profile:

```bash
export BROWSER_USE_API_KEY=your_key && curl -fsSL https://browser-use.com/profile.sh | sh
```

```python
@sandbox(cloud_profile_id="your-profile-id")
async def authenticated_task(browser: Browser):
    ...
```

---

## 9. Common Patterns & Examples

### Pattern: Scrape with CodeAgent + CSV Output

```python
import asyncio
from browser_use.code_use import CodeAgent
from dotenv import load_dotenv

load_dotenv()

TASK = """\
Navigate to https://example.com/products.
Extract every product's name, price, and URL.
Save all results to products.csv with columns: Name, Price, URL.
Call done("Saved N products") when finished.
"""

async def main():
    agent = CodeAgent(task=TASK, max_steps=100)
    await agent.run()
    await agent.close()

asyncio.run(main())
```

### Pattern: Agent with Structured Output

```python
from pydantic import BaseModel

class TopPost(BaseModel):
    title: str
    url: str
    points: int

agent = Agent(
    task="Find the #1 post on Hacker News",
    llm=ChatBrowserUse(),
    output_model_schema=TopPost,
)
result = await agent.run()
```

### Pattern: Fallback Model

```python
agent = Agent(
    task="...",
    llm=ChatAnthropic(model="claude-sonnet-4-0"),
    fallback_llm=ChatOpenAI(model="gpt-4.1"),
)
```

### Pattern: Domain-Restricted Browser

```python
browser = Browser(
    allowed_domains=["*.ycombinator.com"],
    headless=True,
)
agent = Agent(task="...", llm=llm, browser=browser)
```

### Pattern: Export CodeAgent Session for Replay

```python
from browser_use.code_use.notebook_export import export_to_ipynb, session_to_python_script

agent = CodeAgent(task="...")
await agent.run()

export_to_ipynb(agent, "session.ipynb")      # Jupyter
script = session_to_python_script(agent)      # .py
with open("session.py", "w") as f:
    f.write(script)
```

---

## Quick Reference: Environment Variables

| Variable | Purpose |
|---|---|
| `BROWSER_USE_API_KEY` | Browser-Use cloud / `ChatBrowserUse` / `CodeAgent` |
| `ANTHROPIC_API_KEY` | Anthropic Claude models |
| `OPENAI_API_KEY` | OpenAI models |
| `GOOGLE_API_KEY` | Google Gemini models |

---

> **Full docs**: [docs.browser-use.com](https://docs.browser-use.com)
> **GitHub**: [github.com/browser-use/browser-use](https://github.com/browser-use/browser-use)
> **Cloud dashboard**: [cloud.browser-use.com](https://cloud.browser-use.com)
