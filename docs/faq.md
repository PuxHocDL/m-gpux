# FAQ and Troubleshooting

## Where are profiles stored?

Profiles are stored in `~/.modal.toml`.

## I get "No configured Modal profiles found"

Run:

```bash
m-gpux account add
```

Then verify with:

```bash
m-gpux account list
```

## I cannot switch to a profile

Ensure the profile exists first:

```bash
m-gpux account list
m-gpux account switch <profile_name>
```

## billing usage fails for one account

Possible causes:

- Invalid token for that profile
- Expired credentials
- Network/API issues

Try updating credentials with `m-gpux account add` using the same profile name.

## hub says script file does not exist

Ensure you run `m-gpux hub` from the folder containing your script, or provide the correct script filename.

## modal command is not found

Install and configure Modal CLI so `modal` is available in your shell PATH.
