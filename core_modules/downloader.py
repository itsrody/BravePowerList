# core_modules/downloader.py

import asyncio
import logging
import pathlib
from parfive import Downloader, Results

# Configure a logger for this module.
# When this module is imported, its logger name will be 'core_modules.downloader'.
logger = logging.getLogger(__name__)

async def download_filter_lists(
    filter_list_urls: list[str],
    downloader_config: dict
) -> dict[str, str]:
    """
    Downloads filter lists from the given URLs concurrently using parfive.

    Args:
        filter_list_urls: A list of URLs pointing to filter list files.
        downloader_config: A dictionary containing downloader-specific
                           configurations, e.g.,
                           {
                               "max_conn": 5,
                               "temp_dir": "./temp_downloads/",
                               "overwrite_temp_files": True
                           }

    Returns:
        A dictionary where keys are the successful URLs and values are the
        raw string content (UTF-8 decoded) of the downloaded filter lists.
    """
    if not filter_list_urls:
        logger.warning("No filter list URLs provided to downloader.")
        return {}

    max_connections = downloader_config.get("max_conn", 5)
    temp_download_path_str = downloader_config.get("temp_dir", "./temp_downloads/")
    overwrite_temp = downloader_config.get("overwrite_temp_files", True)

    # The temp_download_path should be relative to the project root (where the script is run)
    # If main_generator.py is in core_modules, and it sets up PROJECT_ROOT correctly,
    # this path could be made absolute or handled carefully.
    # For now, assume it's relative to CWD.
    temp_download_path = pathlib.Path(temp_download_path_str)
    try:
        temp_download_path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured temporary download directory exists: {temp_download_path.resolve()}")
    except OSError as e:
        logger.error(f"Could not create temporary download directory {temp_download_path.resolve()}: {e}")
        return {} # Fail if temp dir cannot be created

    downloader = Downloader(
        max_conn=max_connections,
        progress=False,
        overwrite=overwrite_temp,
        config_dir=False # Prevent parfive from creating its own .parfive config directory
    )

    downloaded_content: dict[str, str] = {}

    if not filter_list_urls:
        logger.info("No URLs to download.")
        return downloaded_content

    logger.info(f"Starting download of {len(filter_list_urls)} filter list(s) into '{temp_download_path.resolve()}'.")

    for url in filter_list_urls:
        if not url or not isinstance(url, str) or not (url.startswith("http://") or url.startswith("https://")):
            logger.warning(f"Skipping invalid or non-HTTP/S URL: {url}")
            continue
        downloader.enqueue_file(url, path=str(temp_download_path)) # Ensure path is string for parfive
        logger.debug(f"Enqueued for download: {url}")

    if not downloader.queued_downloads:
        logger.info("No valid URLs were enqueued for download.")
        # Clean up temp_download_path if it was created and is empty
        try:
            if temp_download_path.exists() and not any(temp_download_path.iterdir()):
                temp_download_path.rmdir()
        except OSError:
            pass # Ignore cleanup error if it fails
        return downloaded_content

    results: Results = await downloader.download()
    logger.info(f"Download process completed. Errors encountered for {len(results.errors_set)} URL(s).")

    for i, downloaded_file_path_obj in enumerate(results):
        original_url = downloader.queued_downloads[i].url
        error = results.errors[i]

        if error:
            logger.error(f"Failed to download {original_url}: {error}")
            partial_file_path = downloader.queued_downloads[i].filepath_partial
            if partial_file_path and partial_file_path.exists():
                try:
                    partial_file_path.unlink()
                    logger.debug(f"Cleaned up partial temporary file: {partial_file_path}")
                except OSError as e_unlink:
                    logger.warning(f"Could not delete partial temporary file {partial_file_path}: {e_unlink}")
            continue

        if downloaded_file_path_obj and downloaded_file_path_obj.exists():
            try:
                logger.debug(f"Successfully downloaded to temporary location: {downloaded_file_path_obj}")
                content = downloaded_file_path_obj.read_text(encoding='utf-8')
                downloaded_content[original_url] = content
                logger.info(f"Successfully downloaded and read content from: {original_url}")
            except Exception as e_read:
                logger.error(f"Error reading downloaded file {downloaded_file_path_obj} for URL {original_url}: {e_read}")
            finally:
                try:
                    downloaded_file_path_obj.unlink()
                    logger.debug(f"Cleaned up temporary file: {downloaded_file_path_obj}")
                except OSError as e_unlink:
                    logger.warning(f"Could not delete temporary file {downloaded_file_path_obj}: {e_unlink}")
        else:
            logger.error(f"Download for {original_url} reported no error, but temp file not found at {downloaded_file_path_obj}.")

    try:
        if temp_download_path.exists() and not any(temp_download_path.iterdir()):
            temp_download_path.rmdir()
            logger.info(f"Successfully removed empty temporary download directory: {temp_download_path.resolve()}")
    except OSError as e:
        logger.warning(f"Could not remove temporary download directory {temp_download_path.resolve()} "
                       f"(it might not be empty or permissions issue): {e}")

    if not downloaded_content:
        logger.warning("No filter lists were successfully downloaded and read.")
    else:
        logger.info(f"Successfully downloaded and processed content for {len(downloaded_content)} "
                    f"out of {len(filter_list_urls)} provided valid URL(s).")

    return downloaded_content
