# Contributing

## Branches

Use short, descriptive branch names:

- `app/tc-lag-cleanup`
- `fix/muskingum-volume-error`
- `docs/add-deployment-notes`

## Pull request checklist

Before asking for review:

- Run the affected app locally.
- Confirm the app starts without import errors.
- Confirm sliders, dropdowns, uploads, and tables still update.
- Update the app README if inputs, assumptions, outputs, or limitations changed.
- Note any intentional simplifications or known issues in the pull request.

## Coding expectations

- Keep engineering calculations readable and close to the equations being taught.
- Prefer clear function names over compact code.
- Validate inputs before model calculations.
- Return readable errors instead of silently clipping invalid cases.
- Use `np.trapezoid`, not `np.trapz`, for new integration code.
- Keep UI callbacks thin. Push computation into named functions.

## Review focus

For these training apps, review should focus on:

1. Does the app still teach one clear concept?
2. Are assumptions visible to the user?
3. Are calculations inspectable?
4. Are validation errors understandable?
5. Are visual comparisons clear and consistent?
