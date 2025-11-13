def build_core_prompt(persona, idea, location):
    appearance = persona["appearance"]["summary"] if "summary" in persona["appearance"] else (
        "young East Asian woman with soft features, long dark hair"
    )

    return (
        f"{appearance}. "
        f"Lifestyle / fitness influencer in Shanghai. "
        f"Photo idea: {idea}. "
        f"Location: {location.get('name', 'Shanghai')}. "
        f"Keep natural iPhone style, no studio look, no cinematic lighting."
    )
