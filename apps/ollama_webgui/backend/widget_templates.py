def build_manifest(widget_id: str, name: str, namespace: str, version: str, author: str) -> str:
    return f'''{{
  "manifest_version": 2.0,
  "id": "{widget_id}",
  "type": "widget",
  "name": "{name}",
  "namespace": "{namespace}",
  "version": "{version}",
  "author": "{author}"
}}
'''

def build_readme(widget_name: str) -> str:
    return f"""# {widget_name}

This is a generated Zabbix widget example.

Files:
- manifest.json
- WidgetView.php
- README.md

Next steps:
1. Review file structure for your Zabbix version.
2. Extend with form/config support.
3. Add API/item/data rendering logic.
"""

def build_widget_view(widget_name: str) -> str:
    return f"""<?php

namespace Modules\\GeneratedWidget\\Views;

class WidgetView
{{
    public static function render(): string
    {{
        return '<div style="padding: 10px;">{widget_name} widget generated successfully.</div>';
    }}
}}
"""

def build_example_php_controller(widget_name: str) -> str:
    return f"""<?php

namespace Modules\\GeneratedWidget\\Actions;

use CController;
use CControllerResponseData;

class WidgetExample extends CController
{{
    protected function checkInput()
    {{
        return true;
    }}

    protected function checkPermissions()
    {{
        return $this->getUserType() >= USER_TYPE_ZABBIX_USER;
    }}

    protected function doAction()
    {{
        $data = [
            'title' => '{widget_name}',
            'message' => 'This is an example widget controller.'
        ];

        $response = new CControllerResponseData($data);
        $this->setResponse($response);
    }}
}}
"""
