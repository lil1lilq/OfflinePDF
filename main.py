import multiprocessing

if __name__ == '__main__':
    multiprocessing.freeze_support()
    from offline_pdf.app import main
    main()
