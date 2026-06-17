# OpenAI 图片和 VQA provider

当你希望通过 OpenAI API 生成图片或执行视觉 QA 时，可以使用 OpenAI。

## 项目配置

```yaml
asset_image_model: openai:gpt-image-2
vqa_model: openai:gpt-5.5
```

## 配置步骤

1. 设置 API key：

```bash
export OPENAI_API_KEY=...
```

2. 安装 Python 包：

```bash
pip install openai
```

3. 运行 `python tools/check_env.py`。
