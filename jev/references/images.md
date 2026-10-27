# Images and Box

Checked 2026-10-27. Jev 1.14 accepts PNG/JPEG image parts and Box questions. Read the current [multimodal format and limits](https://openrouter.ai/docs/guides/community/multimodal-decisions) before preparing media; these features may change between releases.

Put a base64 data URL in `state`, preferably a top-level array alongside plain strings:

```python
import base64
from pathlib import Path
image = base64.b64encode(Path("scene.png").read_bytes()).decode("ascii")
request = {
    "model": "typesafe/jev-1.14",
    "state": [
        "Current screenshot; identify the search field, including its border.",
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + image}}
    ],
    "questions": {
        "present": {"type": "noul", "instructions": "Is a search field visible in the screenshot?"},
        "target": {"type": "box", "instructions": "the search field, including its outer border"}
    }
}
```

Remote image URLs are not fetched. A filesystem name, raw base64 string or Responses API `input_image` part is not this image format. Normalize orientation and check dimensions/size against the linked limits; embedding base64 expands the request. The helper's local byte bounds do not validate image dimensions or prove provider acceptance.

Box returns `top`, `bottom`, `left`, `right` in `[0,1]`, relative to image height/width from the upper-left corner. Scale x values by the original image width and y by height. Box always returns bounds, even if the target is absent; use the accompanying presence judgment and inspect the image. A box is a candidate location, not proof that a click succeeded. Recheck the live state before acting if the screenshot or viewport changed. [Box behavior](https://openrouter.ai/blog/insights/what-is-jev/).
