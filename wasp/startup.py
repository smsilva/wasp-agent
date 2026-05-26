import logging
import os
import sys

from wasp.gitops_committer import GitOpsCommitter
from wasp.logging import configure_logging


def startup() -> None:
    configure_logging()

    try:
        GitOpsCommitter.probe()
    except RuntimeError as e:
        logging.getLogger(__name__).error("startup: %s", e)
        sys.exit(1)

    os.umask(0o077)
