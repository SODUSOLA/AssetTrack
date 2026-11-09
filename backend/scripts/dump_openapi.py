"""Write the API's OpenAPI document, the source of the frontend's generated types.

    (cd backend && poetry run python -m scripts.dump_openapi > ../frontend/openapi.json)

The output is stable (sorted keys), so a stale copy shows up as a diff in CI.
"""

import json
import sys

from app.main import app


def main() -> None:
    json.dump(app.openapi(), sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
