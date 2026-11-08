import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    # Build verification only; it makes no network connection.
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from offline_pdf.diagnostics import run_diagnostic

        raise SystemExit(run_diagnostic(sys.argv[1], sys.argv[2]))
    from offline_pdf.explorer import ExplorerInbox, parse_args, register_menu

    args = parse_args(sys.argv[1:])
    inbox = None
    if args.register_explorer or args.unregister_explorer or args.explorer:
        import os

        if os.name != "nt":
            raise SystemExit("Explorer integration requires Windows.")
    if args.register_explorer or args.unregister_explorer:
        register_menu(remove=args.unregister_explorer)
        raise SystemExit(0)
    if args.explorer:
        inbox = ExplorerInbox()
        inbox.submit(args.explorer, args.files)
        if not inbox.owner:
            raise SystemExit(0)
    from offline_pdf.app import main

    main(inbox=inbox, files=args.files if not args.explorer else None)
