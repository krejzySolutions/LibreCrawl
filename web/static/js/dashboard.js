// ========================================
// Dashboard Functions
// ========================================

async function openDashboard() {
    const modal = document.getElementById('dashboardModal');
    const content = document.getElementById('dashboardContent');

    // Show modal
    modal.style.display = 'flex';

    // Load crawls
    try {
        const response = await fetch('/api/crawls/list');
        const data = await response.json();

        if (!data.success) {
            content.innerHTML = `<p style="color: #ef4444;">Error loading crawls: ${data.error}</p>`;
            return;
        }

        const crawls = data.crawls || [];

        if (crawls.length === 0) {
            content.innerHTML = `<p style="text-align: center; color: #9ca3af;">No saved crawls found.</p>`;
            return;
        }

        // Build table
        let html = `
            <table class="data-table" style="width: 100%; table-layout: fixed;">
                <thead>
                    <tr>
                        <th style="width: 180px;">Date</th>
                        <th style="width: 200px;">Domain</th>
                        <th style="width: 80px;">URLs</th>
                        <th style="width: 100px;">Status</th>
                        <th style="width: 280px;">Actions</th>
                    </tr>
                </thead>
                <tbody>
        `;

        crawls.forEach(crawl => {
            const date = new Date(crawl.started_at).toLocaleString();
            const domain = crawl.base_domain || crawl.base_url;
            const status = crawl.status || 'unknown';
            const statusColor = status === 'completed' ? '#10b981' : status === 'running' ? '#3b82f6' : status === 'paused' ? '#f59e0b' : '#6b7280';

            html += `
                <tr>
                    <td>${date}</td>
                    <td>${domain}</td>
                    <td>${crawl.urls_crawled || 0}</td>
                    <td><span style="color: ${statusColor};">${status}</span></td>
                    <td style="white-space: nowrap;">
                        <button class="btn btn-primary" style="margin-right: 5px; padding: 6px 12px; font-size: 13px;" onclick="loadCrawlFromDashboard(${crawl.id})">Load</button>
                        <button class="btn btn-secondary" style="margin-right: 5px; padding: 6px 12px; font-size: 13px;" onclick="resumeCrawlFromDashboard(${crawl.id})">Resume</button>
                        <button class="btn btn-danger" style="padding: 6px 12px; font-size: 13px;" onclick="deleteCrawlFromDashboard(${crawl.id})">Delete</button>
                    </td>
                </tr>
            `;
        });

        html += `
                </tbody>
            </table>
        `;

        content.innerHTML = html;

    } catch (error) {
        console.error('Error loading dashboard:', error);
        content.innerHTML = `<p style="color: #ef4444;">Error loading crawls.</p>`;
    }
}

function closeDashboard() {
    document.getElementById('dashboardModal').style.display = 'none';
}

async function loadCrawlFromDashboard(crawlId) {
    if (!confirm('Load this crawl? Any unsaved current data will be lost.')) return;

    try {
        // Call backend to load data into current crawler
        const response = await fetch(`/api/crawls/${crawlId}/load`, {
            method: 'POST'
        });
        const data = await response.json();

        if (!data.success) {
            alert('Error: ' + (data.error || data.message));
            return;
        }

        // Close dashboard
        closeDashboard();

        // Clear UI and reset state
        clearAllTables();
        resetStats();
        crawlState.urls = [];
        crawlState.links = [];
        crawlState.issues = [];
        crawlState.baseUrl = data.crawl?.base_url || '';
        crawlState.stats = {
            discovered: data.urls_count || 0,
            crawled: data.urls_count || 0,
            depth: data.crawl?.max_depth_reached || 0,
            speed: 0
        };

        // Set URL input
        if (crawlState.baseUrl) {
            document.getElementById('urlInput').value = crawlState.baseUrl;
        }

        // Switch virtual scrollers to windowed (paginated) mode.
        // The backend no longer loads all rows into memory, so we fetch pages
        // on demand from /api/crawl_data instead of reading from crawlState.urls.
        // url_stats carries the SQL-computed filter-sidebar breakdown.
        switchScrollersToWindowed({
            urls: data.urls_count || 0,
            links: data.links_count || 0,
            issues: data.issues_count || 0,
            url_stats: data.url_stats || null
        });

        // Update displays
        updateStatsDisplay();
        updateFilterCounts();
        updateCrawlButtons();
        updateStatus(`Loaded: ${(data.urls_count || 0).toLocaleString()} URLs`);

        showNotification('Crawl loaded successfully', 'success');

    } catch (error) {
        console.error('Error loading crawl:', error);
        alert('Error loading crawl');
    }
}

async function resumeCrawlFromDashboard(crawlId) {
    if (!confirm('Resume this crawl? Any unsaved current data will be lost.')) return;

    try {
        // Call backend to resume
        const response = await fetch(`/api/crawls/${crawlId}/resume`, {
            method: 'POST'
        });
        const data = await response.json();

        if (!data.success) {
            alert('Error: ' + (data.error || data.message));
            return;
        }

        // Close dashboard
        closeDashboard();

        // A resumed crawl is live — restore owned-mode scrollers if we were
        // previously viewing a historical crawl in windowed mode.
        if (typeof _windowedTotals !== 'undefined' && _windowedTotals !== null) {
            switchScrollersToOwned();
        }

        // Fetch the loaded data
        const statusResponse = await fetch('/api/crawl_status');
        const statusData = await statusResponse.json();

        // Clear UI
        clearAllTables();
        resetStats();

        // Populate data
        crawlState.urls = [];
        crawlState.links = statusData.links || [];
        crawlState.issues = statusData.issues || [];
        crawlState.stats = statusData.stats || {};
        crawlState.baseUrl = statusData.stats?.baseUrl || '';

        // Set URL input
        if (crawlState.baseUrl) {
            document.getElementById('urlInput').value = crawlState.baseUrl;
        }

        // Add URLs to tables
        if (statusData.urls && statusData.urls.length > 0) {
            statusData.urls.forEach(url => addUrlToTable(url));
        }

        // Load links
        if (statusData.links && statusData.links.length > 0) {
            crawlState.pendingLinks = statusData.links;
        }

        // Load issues
        if (statusData.issues && statusData.issues.length > 0) {
            crawlState.pendingIssues = statusData.issues;
        }

        // Set crawl as running
        if (statusData.status === 'running') {
            crawlState.isRunning = true;
            crawlState.isPaused = false;
            crawlState.startTime = new Date();
            showProgress();
            updateCrawlButtons();
            pollCrawlProgress();
        }

        // Update displays
        updateStatsDisplay();
        updateFilterCounts();
        updateStatusCodesTable();
        updateStatus('Crawl resumed');

        showNotification('Crawl resumed successfully', 'success');

    } catch (error) {
        console.error('Error resuming crawl:', error);
        alert('Error resuming crawl');
    }
}

async function deleteCrawlFromDashboard(crawlId) {
    if (!confirm('Delete this crawl permanently? This cannot be undone.')) return;

    try {
        const response = await fetch(`/api/crawls/${crawlId}/delete`, {
            method: 'DELETE'
        });
        const data = await response.json();

        if (data.success) {
            showNotification('Crawl deleted', 'success');
            // Reload dashboard
            openDashboard();
        } else {
            alert('Error deleting crawl: ' + data.error);
        }
    } catch (error) {
        console.error('Error deleting crawl:', error);
        alert('Error deleting crawl');
    }
}
