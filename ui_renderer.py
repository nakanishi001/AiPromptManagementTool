import streamlit as st


def render_custom_fields(config):
    fields = config["custom_fields"]
    if not fields:
        return []

    st.subheader("入力補助")
    prompt_values = []
    for field in fields:
        widget_key = f"ui_field_{field['id']}_{field['type']}"
        widget_args = {"label": field["label"], "key": widget_key}
        if field["help"]:
            widget_args["help"] = field["help"]

        if field["type"] == "text_input":
            value = st.text_input(
                placeholder=field["placeholder"] or None,
                **widget_args,
            )
        elif field["type"] == "text_area":
            value = st.text_area(
                height=100,
                placeholder=field["placeholder"] or None,
                **widget_args,
            )
        elif field["type"] == "selectbox":
            value = st.selectbox(options=field["options"], **widget_args)
        elif field["type"] == "multiselect":
            value = st.multiselect(options=field["options"], **widget_args)
        else:
            value = st.checkbox(**widget_args)

        if field["include_in_prompt"] and value:
            if isinstance(value, list):
                formatted_value = ", ".join(value)
            elif isinstance(value, bool):
                formatted_value = "有効" if value else "無効"
            else:
                formatted_value = value
            prompt_values.append((field["label"], formatted_value))

    return prompt_values


def append_custom_values(request, prompt_values):
    if not prompt_values:
        return request

    lines = [f"- {label}: {value}" for label, value in prompt_values]
    return f"{request.rstrip()}\n\n補助入力:\n" + "\n".join(lines)