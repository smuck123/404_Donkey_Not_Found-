# 404_Donkey_Not_Found-

## Chat Admin WebGUI environment configuration

The backend at `apps/chat_admin_webgui/backend/app.py` now reads its image-generation settings from environment variables so local deployments can change service endpoints and limits without editing code.

### Required environment variables

Set these values before starting the Chat Admin WebGUI backend:

- `IMAGE_API_BASE_URL` — base URL for the image API service.
- `DEFAULT_IMAGE_WORKFLOW` — workflow name or identifier the backend should use by default.
- `IMAGE_OUTPUT_DIR` — absolute or repo-relative path where generated images should be written.
- `MAX_IMAGE_SIZE` — maximum accepted image dimension/size setting as an integer.
- `MAX_BATCH_COUNT` — maximum number of images allowed in a single batch request.
- `REQUEST_TIMEOUT` — request timeout, in seconds, for image-service calls.

### Example values for local deployment

```bash
export IMAGE_API_BASE_URL="http://127.0.0.1:8188"
export DEFAULT_IMAGE_WORKFLOW="sdxl_text2img"
export IMAGE_OUTPUT_DIR="/workspace/404_Donkey_Not_Found-/apps/chat_admin_webgui/generated_images"
export MAX_IMAGE_SIZE="4096"
export MAX_BATCH_COUNT="8"
export REQUEST_TIMEOUT="120"
```

### Related optional backend variables

The backend also supports these existing service settings for local development:

```bash
export OLLAMA_TAGS_URL="http://127.0.0.1:11434/api/tags"
export OLLAMA_CHAT_URL="http://127.0.0.1:11434/api/chat"
export DEFAULT_MODEL="qwen3:8b"
export SEARCH_API_URL="http://127.0.0.1:8020/search"
```
