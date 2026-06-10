<p align="center">
  <img src="docs/banner.svg" alt="NIM Stream Proxy" width="700"/>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT License"/></a>
  <img src="https://img.shields.io/badge/python-3-blue?style=flat-square&logo=python&logoColor=white" alt="Python 3"/>
  <img src="https://img.shields.io/badge/NVIDIA-NIM-76b900?style=flat-square&logo=nvidia&logoColor=white" alt="NVIDIA NIM"/>
  <img src="https://img.shields.io/badge/OpenAI-API_compatible-412991?style=flat-square" alt="OpenAI compatible"/>
</p>

Local proxy that forces NVIDIA NIM streaming mode for non-streaming requests, then reassembles the response into a single block. Prevents timeouts on large models (70B+) that take too long to generate a full response in one shot.

## Problem

The NVIDIA NIM free tier has aggressive timeouts on non-streaming requests. Large models (Llama 3.1 70B, Qwen 72B, etc.) often fail with 524 errors because they can't complete the response fast enough. Streaming mode doesn't have this problem.

## Solution

This proxy intercepts `/chat/completions` requests:
- **Non-streaming request** → forces `stream: true` to NVIDIA, collects all chunks, reassembles into a standard non-streaming response
- **Streaming request** → passes through untouched
- **Other endpoints** → passes through untouched

Your client sees a normal non-streaming response. NVIDIA sees a streaming request that won't timeout.

## Usage

```bash
export NVIDIA_API_KEY="nvapi-..."
python3 proxy.py
```

Then point your client to `http://127.0.0.1:11436` with an OpenAI-compatible base URL:

```bash
# Example with curl
curl http://127.0.0.1:11436/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "meta/llama-3.1-70b-instruct", "messages": [{"role": "user", "content": "Hello"}]}'
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `NVIDIA_API_KEY` | (required) | Your NVIDIA NIM API key |
| `NIM_PROXY_PORT` | `11436` | Port to listen on |

## Dependencies

Python 3 standard library only. No pip install needed.
