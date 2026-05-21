/**
 * Virtual Scrolling implementation for large table datasets
 * Only renders visible rows + buffer for smooth scrolling
 *
 * Modes:
 *   'owned'    (default) — caller passes full data array via setData()/appendData().
 *   'windowed' — scroller fetches pages on demand via a fetchPage(offset, limit) callback.
 */

class VirtualScroller {
    constructor(container, options = {}) {
        this.container = container;
        this.tableBody = container.querySelector('tbody');
        this.data = [];

        // Configuration
        this.rowHeight = options.rowHeight || 40; // px per row
        this.buffer = options.buffer || 10; // extra rows to render above/below viewport
        this.columnCount = options.columnCount || 1;
        this.renderRow = options.renderRow || this.defaultRenderRow.bind(this);

        // Mode: 'owned' (default) or 'windowed'
        this.mode = options.mode || 'owned';

        // Windowed-mode state
        this.totalCount = 0;
        this.pageSize = options.pageSize || 1000;
        this._fetchPageFn = options.fetchPage || null;
        this._pageCache = new Map();   // pageIndex -> rowArray (LRU: oldest at head)
        this._inFlight = new Set();    // pageIndex set of in-progress requests
        this._generation = 0;          // incremented on reset() to discard stale responses
        this._fetchDebounceTimer = null;
        this._maxCachedPages = 10;

        // State
        this.scrollTop = 0;
        this.containerHeight = 0;
        this.visibleStart = 0;
        this.visibleEnd = 0;

        // Create virtual scrolling structure
        this.setupVirtualScroll();

        // Bind scroll handler
        this.handleScroll = this.handleScroll.bind(this);
        this.container.addEventListener('scroll', this.handleScroll, { passive: true });

        // Observe container size changes
        this.resizeObserver = new ResizeObserver(() => this.updateViewport());
        this.resizeObserver.observe(this.container);
    }

    // ---------------------------------------------------------------------------
    // Internal helper: single source of truth for total row count
    // ---------------------------------------------------------------------------
    _getRowCount() {
        return this.mode === 'windowed' ? this.totalCount : this.data.length;
    }

    setupVirtualScroll() {
        // Get column count from table header
        const table = this.tableBody.parentElement;
        const headerRow = table.querySelector('thead tr');
        const columnCount = headerRow ? headerRow.children.length : 1;

        // Create spacer rows for virtual scrolling (top and bottom padding)
        this.topSpacer = document.createElement('tr');
        const topCell = document.createElement('td');
        topCell.colSpan = columnCount;
        topCell.style.height = '0px';
        topCell.style.padding = '0';
        topCell.style.border = 'none';
        topCell.style.pointerEvents = 'none';
        this.topSpacer.appendChild(topCell);

        this.bottomSpacer = document.createElement('tr');
        const bottomCell = document.createElement('td');
        bottomCell.colSpan = columnCount;
        bottomCell.style.height = '0px';
        bottomCell.style.padding = '0';
        bottomCell.style.border = 'none';
        bottomCell.style.pointerEvents = 'none';
        this.bottomSpacer.appendChild(bottomCell);

        // Insert spacers at top and bottom of tbody
        this.tableBody.insertBefore(this.topSpacer, this.tableBody.firstChild);
        this.tableBody.appendChild(this.bottomSpacer);

        // Ensure container can scroll
        this.container.style.overflowY = 'auto';
        this.container.style.overflowX = 'auto';
        this.container.style.position = 'relative';

        console.log('VirtualScroller initialized with', columnCount, 'columns');
    }

    // ---------------------------------------------------------------------------
    // Owned-mode API (unchanged)
    // ---------------------------------------------------------------------------

    setData(data) {
        this.data = data;
        this.updateScrollHeight();
        // Force render by resetting visible range to ensure UI updates
        this.visibleStart = -1;
        this.visibleEnd = -1;
        this.render();
    }

    appendData(newData) {
        if (this.mode === 'windowed') {
            console.warn('VirtualScroller: appendData() is not supported in windowed mode. Use setTotalCount() instead.');
            return;
        }
        this.data.push(...newData);
        this.updateScrollHeight();
        this.render();
    }

    updateScrollHeight() {
        // Total height is set via spacer rows, not needed here
        // The spacers will be adjusted during render
    }

    updateViewport() {
        this.containerHeight = this.container.clientHeight;
        this.render();
    }

    handleScroll() {
        this.scrollTop = this.container.scrollTop;
        this.render();
    }

    getVisibleRange() {
        const rowCount = this._getRowCount();
        const start = Math.floor(this.scrollTop / this.rowHeight);
        const visibleCount = Math.ceil(this.containerHeight / this.rowHeight);

        // Add buffer
        const bufferedStart = Math.max(0, start - this.buffer);
        const bufferedEnd = Math.min(rowCount, start + visibleCount + this.buffer);

        return {
            start: Math.floor(bufferedStart),
            end: Math.ceil(bufferedEnd)
        };
    }

    render() {
        // A destroyed/replaced scroller must never touch the DOM again — a stale
        // ResizeObserver or debounced fetch could otherwise strip the spacers of
        // the live scroller that replaced it.
        if (this._destroyed) return;
        // Defensive: if our spacers were detached (tbody wiped externally),
        // re-attach them rather than crashing in insertBefore().
        if (!this.tableBody.contains(this.bottomSpacer) ||
            !this.tableBody.contains(this.topSpacer)) {
            this.tableBody.insertBefore(this.topSpacer, this.tableBody.firstChild);
            this.tableBody.appendChild(this.bottomSpacer);
        }

        const rowCount = this._getRowCount();

        if (!rowCount) {
            // Clear all rows except spacers
            const existingRows = Array.from(this.tableBody.children).filter(
                child => child !== this.topSpacer && child !== this.bottomSpacer
            );
            existingRows.forEach(row => row.remove());

            if (this.topSpacer && this.topSpacer.firstChild) {
                this.topSpacer.firstChild.style.height = '0px';
            }
            if (this.bottomSpacer && this.bottomSpacer.firstChild) {
                this.bottomSpacer.firstChild.style.height = '0px';
            }
            return;
        }

        const { start, end } = this.getVisibleRange();

        // Only re-render if range changed by at least 1 row to reduce flickering
        // Reduced threshold from 3 to 1 to fix fast scrolling issue
        // In windowed mode this short-circuit is also bypassed from _onPageArrived
        const threshold = 1;
        if (Math.abs(start - this.visibleStart) < threshold &&
            Math.abs(end - this.visibleEnd) < threshold) {
            return;
        }

        this.visibleStart = start;
        this.visibleEnd = end;

        // Calculate spacer heights
        const topHeight = start * this.rowHeight;
        const bottomHeight = (rowCount - end) * this.rowHeight;

        // Update spacers (set height on the TD cells)
        this.topSpacer.firstChild.style.height = topHeight + 'px';
        this.bottomSpacer.firstChild.style.height = bottomHeight + 'px';

        // Remove existing data rows (keep spacers)
        const existingRows = Array.from(this.tableBody.children).filter(
            child => child !== this.topSpacer && child !== this.bottomSpacer
        );
        existingRows.forEach(row => row.remove());

        // Create and insert new rows
        const fragment = document.createDocumentFragment();
        let needsFetch = false;

        for (let i = start; i < end; i++) {
            let row;
            if (this.mode === 'windowed') {
                const pageIndex = Math.floor(i / this.pageSize);
                const page = this._getCachedPage(pageIndex);
                if (page) {
                    const rowData = page[i - pageIndex * this.pageSize];
                    row = this.createRow(rowData, i);
                } else {
                    row = this._createPlaceholderRow(i);
                    needsFetch = true;
                }
            } else {
                row = this.createRow(this.data[i], i);
            }
            fragment.appendChild(row);
        }

        // Insert rows between spacers
        this.tableBody.insertBefore(fragment, this.bottomSpacer);

        // Schedule page fetches for missing data (debounced)
        if (this.mode === 'windowed' && needsFetch) {
            this._scheduleFetch();
        }
    }

    createRow(rowData, index) {
        const row = document.createElement('tr');
        row.dataset.index = index;

        // Use custom render function
        this.renderRow(row, rowData, index);

        return row;
    }

    defaultRenderRow(row, rowData, index) {
        // Default: assume rowData is array of cell values
        if (Array.isArray(rowData)) {
            rowData.forEach(cellData => {
                const cell = document.createElement('td');
                if (typeof cellData === 'string' && cellData.includes('<button')) {
                    cell.innerHTML = cellData;
                } else {
                    cell.textContent = cellData;
                }
                row.appendChild(cell);
            });
        } else {
            // Single cell with stringified data
            const cell = document.createElement('td');
            cell.textContent = JSON.stringify(rowData);
            row.appendChild(cell);
        }
    }

    clear() {
        this.data = [];
        this.visibleStart = 0;
        this.visibleEnd = 0;

        // Remove all rows except spacers
        const existingRows = Array.from(this.tableBody.children).filter(
            child => child !== this.topSpacer && child !== this.bottomSpacer
        );
        existingRows.forEach(row => row.remove());

        // Reset spacer heights
        if (this.topSpacer && this.topSpacer.firstChild) {
            this.topSpacer.firstChild.style.height = '0px';
        }
        if (this.bottomSpacer && this.bottomSpacer.firstChild) {
            this.bottomSpacer.firstChild.style.height = '0px';
        }

        console.log('Virtual scroller cleared');
    }

    destroy() {
        // Mark destroyed first so any in-flight callback (ResizeObserver,
        // debounced fetch, page-arrival) that fires during teardown is a no-op.
        this._destroyed = true;
        this.container.removeEventListener('scroll', this.handleScroll);
        if (this.resizeObserver) this.resizeObserver.disconnect();
        if (this._fetchDebounceTimer) {
            clearTimeout(this._fetchDebounceTimer);
            this._fetchDebounceTimer = null;
        }
        // Remove our own spacer rows so a freshly-created scroller starts clean.
        if (this.topSpacer && this.topSpacer.parentNode) this.topSpacer.remove();
        if (this.bottomSpacer && this.bottomSpacer.parentNode) this.bottomSpacer.remove();
    }

    // ---------------------------------------------------------------------------
    // Windowed-mode public API
    // ---------------------------------------------------------------------------

    /**
     * Sets the total number of rows known to exist server-side.
     * Triggers a re-render so scroll geometry updates immediately.
     */
    setTotalCount(n) {
        this.totalCount = n;
        // Force re-render by invalidating cached range
        this.visibleStart = -1;
        this.visibleEnd = -1;
        this.render();
    }

    /**
     * Stores the async page-fetch callback.
     * fn(offset, limit) must return a Promise<rowArray>.
     */
    setFetchPage(fn) {
        this._fetchPageFn = fn;
        // Invalidate cache since the data source changed
        this._generation++;
        this._pageCache.clear();
        this._inFlight.clear();
    }

    /**
     * Clears page cache, in-flight requests, and totalCount; clears rendered rows.
     * Call when switching crawls or when a filter/sort changes.
     */
    reset() {
        this._generation++;
        this._pageCache.clear();
        this._inFlight.clear();
        if (this._fetchDebounceTimer !== null) {
            clearTimeout(this._fetchDebounceTimer);
            this._fetchDebounceTimer = null;
        }
        this.totalCount = 0;
        this.visibleStart = 0;
        this.visibleEnd = 0;

        // Clear rendered rows and reset spacers
        const existingRows = Array.from(this.tableBody.children).filter(
            child => child !== this.topSpacer && child !== this.bottomSpacer
        );
        existingRows.forEach(row => row.remove());

        if (this.topSpacer && this.topSpacer.firstChild) {
            this.topSpacer.firstChild.style.height = '0px';
        }
        if (this.bottomSpacer && this.bottomSpacer.firstChild) {
            this.bottomSpacer.firstChild.style.height = '0px';
        }
    }

    // ---------------------------------------------------------------------------
    // Windowed-mode internals
    // ---------------------------------------------------------------------------

    /**
     * Returns the cached page array and updates its LRU position.
     * Returns null if the page is not cached.
     */
    _getCachedPage(pageIndex) {
        if (!this._pageCache.has(pageIndex)) return null;
        const page = this._pageCache.get(pageIndex);
        // LRU bump: delete then re-insert moves to tail (most-recently-used)
        this._pageCache.delete(pageIndex);
        this._pageCache.set(pageIndex, page);
        return page;
    }

    /**
     * Stores a page in the cache and evicts LRU pages if over the limit.
     */
    _storePage(pageIndex, rows) {
        // Remove existing entry to re-insert at tail
        if (this._pageCache.has(pageIndex)) {
            this._pageCache.delete(pageIndex);
        }
        this._pageCache.set(pageIndex, rows);

        // Evict oldest (head) entries when over capacity
        while (this._pageCache.size > this._maxCachedPages) {
            const oldestKey = this._pageCache.keys().next().value;
            this._pageCache.delete(oldestKey);
        }
    }

    /**
     * Creates a placeholder <tr> of exact rowHeight so scroll geometry stays correct.
     */
    _createPlaceholderRow(index) {
        const row = document.createElement('tr');
        row.dataset.index = index;
        row.dataset.placeholder = 'true';

        const cell = document.createElement('td');
        // Use the same table's column count
        const table = this.tableBody.parentElement;
        const headerRow = table.querySelector('thead tr');
        cell.colSpan = headerRow ? headerRow.children.length : 1;
        cell.style.height = this.rowHeight + 'px';
        cell.style.padding = '0';
        cell.style.color = '#999';
        cell.style.textAlign = 'center';
        cell.style.fontSize = '0.85em';
        cell.textContent = 'Loading…';

        row.appendChild(cell);
        return row;
    }

    /**
     * Debounced fetch scheduler. Fires 120ms after the last scroll event.
     */
    _scheduleFetch() {
        if (this._fetchDebounceTimer !== null) {
            clearTimeout(this._fetchDebounceTimer);
        }
        this._fetchDebounceTimer = setTimeout(() => {
            this._fetchDebounceTimer = null;
            this._fetchVisiblePages();
        }, 120);
    }

    /**
     * Dispatches fetches for all pages covering the current visible range
     * that are not yet cached and not already in-flight.
     */
    _fetchVisiblePages() {
        if (!this._fetchPageFn) return;

        const { start, end } = this.getVisibleRange();
        const firstPage = Math.floor(start / this.pageSize);
        const lastPage = Math.floor(Math.max(0, end - 1) / this.pageSize);

        for (let p = firstPage; p <= lastPage; p++) {
            if (this._pageCache.has(p) || this._inFlight.has(p)) continue;
            this._inFlight.add(p);
            this._loadPage(p, this._generation);
        }
    }

    /**
     * Fetches a single page and stores it in the cache when resolved.
     * Discards the result if the generation has changed (reset() was called).
     */
    _loadPage(pageIndex, generation) {
        const offset = pageIndex * this.pageSize;
        const limit = this.pageSize;

        Promise.resolve(this._fetchPageFn(offset, limit))
            .then(rows => {
                // Discard stale responses
                if (generation !== this._generation) return;

                this._inFlight.delete(pageIndex);
                this._storePage(pageIndex, rows);
                this._onPageArrived(pageIndex);
            })
            .catch(err => {
                if (generation !== this._generation) return;
                this._inFlight.delete(pageIndex);
                console.error('VirtualScroller: fetchPage error for page', pageIndex, err);
            });
    }

    /**
     * Called when a fetched page lands. Re-renders if any rows from that
     * page are still within the current visible range.
     */
    _onPageArrived(pageIndex) {
        const pageStart = pageIndex * this.pageSize;
        const pageEnd = pageStart + this.pageSize;

        // Check if this page overlaps the current visible range
        if (pageEnd > this.visibleStart && pageStart < this.visibleEnd) {
            // Force re-render by invalidating cached range so short-circuit doesn't skip us
            this.visibleStart = -1;
            this.visibleEnd = -1;
            this.render();
        }
    }
}

// Export for use in app.js
window.VirtualScroller = VirtualScroller;
