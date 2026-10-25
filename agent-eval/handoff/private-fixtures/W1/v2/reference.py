def paginate(items, page, page_size):
    if type(page) is not int or type(page_size) is not int or page < 1 or page_size < 1:
        raise ValueError("positive integer page and page_size required")
    total = (len(items) + page_size - 1) // page_size
    start = (page - 1) * page_size
    return {"items": list(items[start:start + page_size]), "total_pages": total, "has_next": page < total}
