"""
工具函数
"""


def preprocess_markdown_for_feishu(text: str) -> str:
    """
    预处理 Markdown 文本，适配飞书 lark_md 格式
    - 将标题 (# H1, ## H2 等) 转换为加粗格式
    - 保留其他 Markdown 语法
    """
    lines = text.split("\n")
    processed_lines = []

    for line in lines:
        # 匹配标题格式 (# Title, ## Title, ### Title 等)
        if line.strip().startswith("#"):
            # 移除 # 符号，提取标题文本
            title_text = line.lstrip("#").strip()
            if title_text:
                # 转换为加粗格式
                processed_lines.append(f"**{title_text}**")
            else:
                processed_lines.append(line)
        else:
            processed_lines.append(line)

    return "\n".join(processed_lines)
