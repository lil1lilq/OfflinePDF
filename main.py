import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    # Build verification only; it makes no network connection.
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from offline_pdf.diagnostics import run_diagnostic

        raise SystemExit(run_diagnostic(sys.argv[1], sys.argv[2]))
    from offline_pdf.app import main

    main()
