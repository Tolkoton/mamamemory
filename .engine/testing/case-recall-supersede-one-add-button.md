# Supersede package — one-add-button, changed by the sealed contract case-recall (F4 S3)

case-recall поправки: «one-add-button Seam («решта гайду — як була») — два нові рядки, supersede
`tests/test_one_add_button.py::test_guide_has_the_plus_line_no_camera_and_the_rest_as_it_was` (своя копія `NEW_GUIDE`)».

- `tests/test_one_add_button.py::test_guide_has_the_plus_line_no_camera_and_the_rest_as_it_was` — `NEW_GUIDE` тримає
  7-рядковий гайд; додати два нові рядки case-recall перед рядком 🔊; рядок «＋ (фото чи файл)» і відсутність 📷 — як були.

Requested: rewrite each listed test to the new contract; `uv run pytest -q` green, except
`tests/test_clarify_disputed.py::test_Q1_…`, which waits for its own package.
