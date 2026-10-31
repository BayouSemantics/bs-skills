# Handling Ignored Assets

These should either be added to `.gitignore` or moved to an already ignored directory. Prefer existing
ignored dirs if they exist and the dir name matches the data category. Prefer organizing non-committed
assets into a common ignored folder rather than bloating `.gitignore`, except in the case of commonly ignored
file types (e.g. `.env`).

Some ephemeral files / code should be classified as throw-away scratch code and deleted. Discuss this
first with the user. Don't delete without his explicit sign-off.