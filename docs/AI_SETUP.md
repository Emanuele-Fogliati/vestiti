# Local AI model

The app talks to any server that speaks the **OpenAI chat-completions API**
(`POST {LLM_BASE_URL}/chat/completions`). Default: **Ollama** running a **Qwen3 8B**
GGUF published by **Unsloth** on Hugging Face. Free, local, no data leaves your machine.

What the model does: reads a trip written in plain words, explains a plan, answers
questions about it. What it does **not** do: decide warmth, layers, products or prices.
Those come from fixed rules, so the plan is the same with or without AI. If the model is
off or slow, the app falls back to a rule-based parser and to the plan's own notes.

## Option A (recommended on Windows): Ollama installed natively

Uses your GPU if you have one. Docker reaches it at `host.docker.internal`.

1. Install Ollama: https://ollama.com/download
2. Pull the model (about 5 GB):
   ```powershell
   ollama pull hf.co/unsloth/Qwen3-8B-GGUF:Q4_K_M
   ```
3. In `.env`:
   ```
   LLM_ENABLED=true
   LLM_BASE_URL=http://host.docker.internal:11434/v1
   LLM_MODEL=hf.co/unsloth/Qwen3-8B-GGUF:Q4_K_M
   ```
4. `docker compose up -d --build`, then check:
   ```powershell
   docker compose exec app python -m app.cli check-ai
   ```
   You want `"available": true` and `parser used: llm`.

If the app can't reach Ollama, set the Windows environment variable
`OLLAMA_HOST=0.0.0.0`, restart Ollama, and try again.

### Your own Unsloth model

Models you trained or saved with Unsloth live on Hugging Face. If you exported a GGUF to
your account (e.g. `your-name/my-qwen-GGUF`), pull it the same way and put the same name
in `LLM_MODEL`:

```powershell
ollama pull hf.co/your-name/my-qwen-GGUF:Q4_K_M
```

Private repos need your Hugging Face token configured in Ollama
(see Ollama's Hugging Face docs). Only GGUF files can be pulled this way.

### Hardware

| Model | RAM / VRAM | Notes |
|---|---|---|
| `hf.co/unsloth/Qwen3-8B-GGUF:Q4_K_M` | ~6 GB | Default. Fast on a GPU, 20–60 s per trip on CPU. |
| `hf.co/unsloth/Qwen3-4B-GGUF:Q4_K_M` | ~3 GB | For laptops without a GPU. Slightly worse parsing. |

Qwen3 "thinks" before answering by default. The app appends `/no_think` and strips any
`<think>` block (set `LLM_DISABLE_THINKING=false` to turn that off).

## Option B: Ollama inside Docker

```powershell
# .env: LLM_BASE_URL=http://ollama:11434/v1
docker compose --profile ollama up -d --build
docker compose exec ollama ollama pull hf.co/unsloth/Qwen3-8B-GGUF:Q4_K_M
```

CPU only unless you uncomment the GPU block in `docker-compose.yml`
(NVIDIA + WSL2 required).

## Option C: llama.cpp or vLLM

- **llama.cpp**: `llama-server -hf unsloth/Qwen3-8B-GGUF:Q4_K_M --port 8080`, then
  `LLM_BASE_URL=http://host.docker.internal:8080/v1`. llama.cpp ignores the model name.
- **vLLM** (Linux + NVIDIA): `vllm serve Qwen/Qwen3-8B --port 8001`, then
  `LLM_BASE_URL=http://host.docker.internal:8001/v1`, `LLM_MODEL=Qwen/Qwen3-8B`.
- **LM Studio** works too (its server is OpenAI-compatible, default port 1234).

## All settings

| Variable | Default | Meaning |
|---|---|---|
| `LLM_ENABLED` | `true` | `false` = never call a model |
| `LLM_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible base URL |
| `LLM_MODEL` | `hf.co/unsloth/Qwen3-8B-GGUF:Q4_K_M` | model name as the server knows it |
| `LLM_API_KEY` | `local` | sent as Bearer token (hosted providers need a real key) |
| `LLM_TIMEOUT_S` | `60` | per request |
| `LLM_DISABLE_THINKING` | `true` | adds `/no_think` for Qwen3 |

## Production

A local model on your PC is fine for development and a closed beta. For a public launch
you need the model on a server (a small GPU VM) or a hosted OpenAI-compatible provider:
change `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY`, no code change. If you switch to a
hosted provider, update the privacy page, which today says trip text stays on our servers.
