const PROVIDERS = {
  groq:      { base: "https://api.groq.com/openai/v1",                          key: "CIPHER_PROXY_GROQ_KEY" },
  gemini:    { base: "https://generativelanguage.googleapis.com/v1beta/openai", key: "CIPHER_PROXY_GEMINI_KEY" },
  deepseek:  { base: "https://api.deepseek.com",                                key: "CIPHER_PROXY_DEEPSEEK_KEY" },
  sambanova: { base: "https://api.sambanova.ai/v1",                             key: "CIPHER_PROXY_SAMBANOVA_KEY" },
  cerebras:  { base: "https://api.cerebras.ai/v1",                              key: "CIPHER_PROXY_CEREBRAS_KEY" },
};

const MODELS = {
  // Groq — fast, free tier
  "llama-3.3-70b":       { provider: "groq",      model: "llama-3.3-70b-versatile" },
  "llama-3.1-8b":        { provider: "groq",      model: "llama-3.1-8b-instant" },
  // Gemini — free tier
  "gemini-2.0-flash":    { provider: "gemini",    model: "gemini-2.0-flash" },
  // DeepSeek — best coding (paid, ~$0.27/1M tokens)
  "deepseek-chat":       { provider: "deepseek",  model: "deepseek-chat" },
  // SambaNova — free fallback
  "sambanova-70b":       { provider: "sambanova", model: "Meta-Llama-3.3-70B-Instruct" },
};

function json(res, code, data) {
  res.writeHead(code, { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" });
  res.end(JSON.stringify(data));
}

module.exports = async (req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") { res.writeHead(200); res.end(); return; }

  const path = req.url.split("?")[0];

  if (req.method === "GET") {
    if (path === "/v1/models") {
      return json(res, 200, { object: "list", data: Object.keys(MODELS).map(id => ({ id, object: "model" })) });
    }
    if (path === "/health") {
      return json(res, 200, { status: "ok" });
    }
    return json(res, 404, { error: "Not found" });
  }

  if (req.method !== "POST" || path !== "/v1/chat/completions") {
    return json(res, 404, { error: "Not found" });
  }

  let body;
  try {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    body = JSON.parse(Buffer.concat(chunks).toString());
  } catch {
    return json(res, 400, { error: "Invalid JSON" });
  }

  const { model, messages, stream = true, temperature = 0.15 } = body;
  const modelCfg = MODELS[model];
  if (!modelCfg) {
    return json(res, 404, { error: `Unknown model: ${model}. Available: ${Object.keys(MODELS).join(", ")}` });
  }

  const provider = PROVIDERS[modelCfg.provider];
  const apiKey = process.env[provider.key] || "";
  const upstreamUrl = `${provider.base}/chat/completions`;

  const payload = {
    model: modelCfg.model,
    messages: messages || [],
    temperature,
    stream: stream !== false,
  };

  const headers = { "Content-Type": "application/json" };
  if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;
  if (modelCfg.provider === "openrouter") {
    headers["HTTP-Referer"] = "https://cipher.elevenpct.com";
    headers["X-Title"] = "Cipher";
  }

  try {
    const upstream = await fetch(upstreamUrl, { method: "POST", headers, body: JSON.stringify(payload) });

    if (!upstream.ok) {
      const errData = await upstream.json().catch(() => ({}));
      return json(res, upstream.status, { error: errData.error?.message || `Upstream returned ${upstream.status}` });
    }

    if (stream === false) {
      const data = await upstream.json();
      return json(res, 200, {
        id: "chatcmpl-" + Math.random().toString(36).slice(2, 8),
        object: "chat.completion", model,
        choices: [{ index: 0, message: { role: "assistant", content: data.choices?.[0]?.message?.content || "" }, finish_reason: "stop" }]
      });
    }

    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "X-Accel-Buffering": "no",
      "Access-Control-Allow-Origin": "*",
    });

    const reader = upstream.body.getReader();
    const decoder = new TextDecoder();
    const rid = "chatcmpl-" + Math.random().toString(36).slice(2, 8);

    let done = false;
    while (!done) {
      const result = await reader.read();
      done = result.done;
      if (done) { res.write("data: [DONE]\n\n"); break; }
      const text = decoder.decode(result.value);
      for (const line of text.split("\n")) {
        if (line.startsWith("data: ")) {
          const d = line.slice(6).trim();
          if (d === "[DONE]") { res.write("data: [DONE]\n\n"); continue; }
          try {
            const parsed = JSON.parse(d);
            const content = parsed.choices?.[0]?.delta?.content || "";
            if (content) {
              res.write("data: " + JSON.stringify({
                id: rid, object: "chat.completion.chunk", model,
                choices: [{ index: 0, delta: { content }, finish_reason: null }]
              }) + "\n\n");
            }
          } catch {}
        }
      }
    }
    res.end();
  } catch (e) {
    json(res, 502, { error: e.message });
  }
};
