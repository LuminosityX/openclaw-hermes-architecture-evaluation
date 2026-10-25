def paginate(items, page, page_size):
    if page < 1 or page_size < 1:
        raise ValueError("positive page and page_size required")
    total = len(items) // page_size
    start = page * page_size
    return {"items": list(items[start:start + page_size]), "total_pages": total, "has_next": page <= total}
