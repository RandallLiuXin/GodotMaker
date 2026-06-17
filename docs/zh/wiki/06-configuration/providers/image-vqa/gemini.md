# Gemini 图片和 VQA provider

当你希望通过 API 后端生成图片或执行视觉 QA 时，可以使用 Gemini。

## 项目配置

```yaml
asset_image_model: gemini:gemini-3.1-flash-image-preview
vqa_model: gemini:gemini-2.5-flash
```

## 配置步骤

1. 创建 Gemini API key。
2. 设置以下任一环境变量：

```bash
export GOOGLE_API_KEY=...
export GEMINI_API_KEY=...
```

3. 安装 Python 包：

```bash
pip install google-genai
```

4. 运行 `python tools/check_env.py`。
