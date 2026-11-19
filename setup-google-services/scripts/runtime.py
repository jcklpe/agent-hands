"""Check the provider's Python minimum without account, token, or network access."""
import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Be silent when the runtime is supported")
    parser.add_argument("--runner", choices=("GOOGLE_PYTHON", "uv"))
    args = parser.parse_args(argv)
    version = ".".join(str(part) for part in sys.version_info[:3])
    if sys.version_info[:2] < (3, 11):
        print("ERROR: Unsupported Python {}: Google capabilities require Python 3.11+. Select an existing compatible executable; no service operation was started.".format(version), file=sys.stderr)
        return 2
    if not args.check:
        print("Python: {} (minimum 3.11; supported)".format(version))
        if args.runner:
            print("Runner: {}".format(args.runner))
        print("No account configuration, credentials, tokens, or service access checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
