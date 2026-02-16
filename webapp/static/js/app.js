/**
 * SMARD Utils Webapp - Frontend Logic
 */

document.addEventListener('DOMContentLoaded', function () {

    // --- File upload handler ---
    const fileInput = document.getElementById('datafile');
    if (fileInput) {
        fileInput.addEventListener('change', function () {
            if (!this.files.length) return;

            const formData = new FormData();
            formData.append('command', 'upload');
            formData.append('datafile', this.files[0]);

            const statusDiv = document.getElementById('upload-status');
            statusDiv.textContent = 'Hochladen...';

            fetch('.', {
                method: 'POST',
                body: formData
            })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'ok') {
                    document.getElementById('uploaded_file').value = data.filename;
                    statusDiv.textContent = `Datei: ${data.filename} (${data.size_kb} KB)`;
                    statusDiv.style.color = '#2c5f2d';
                } else {
                    statusDiv.textContent = `Fehler: ${data.message}`;
                    statusDiv.style.color = '#c62828';
                    document.getElementById('uploaded_file').value = '';
                }
            })
            .catch(err => {
                statusDiv.textContent = `Upload fehlgeschlagen: ${err}`;
                statusDiv.style.color = '#c62828';
            });
        });
    }

    // --- Analysis form handler ---
    const analysisForm = document.getElementById('analysis-form');
    if (analysisForm) {
        analysisForm.addEventListener('submit', function (e) {
            e.preventDefault();

            const btn = document.getElementById('run-btn');
            btn.disabled = true;
            btn.textContent = 'Analyse laeuft...';

            // Show loading, hide results
            document.getElementById('loading').style.display = 'block';
            document.getElementById('chart-container').style.display = 'none';
            document.getElementById('table-container').style.display = 'none';
            document.getElementById('error-container').style.display = 'none';

            const formData = new FormData(analysisForm);

            fetch('.', {
                method: 'POST',
                body: formData
            })
            .then(r => r.json())
            .then(data => {
                document.getElementById('loading').style.display = 'none';
                btn.disabled = false;
                btn.textContent = 'Analyse starten';

                if (data.status === 'success') {
                    // Show table
                    if (data.table_text) {
                        document.getElementById('results-table').textContent = data.table_text;
                        document.getElementById('table-container').style.display = 'block';
                    }

                    // Show chart
                    if (data.chart_url) {
                        const chartImg = document.getElementById('chart-img');
                        chartImg.src = data.chart_url + '&t=' + Date.now();
                        document.getElementById('chart-container').style.display = 'block';

                        document.getElementById('download-svg').href = data.chart_url;
                    }

                    if (data.csv_url) {
                        document.getElementById('download-csv').href = data.csv_url;
                    }
                } else {
                    document.getElementById('error-message').textContent = data.message || 'Unknown error';
                    document.getElementById('error-container').style.display = 'block';
                }
            })
            .catch(err => {
                document.getElementById('loading').style.display = 'none';
                btn.disabled = false;
                btn.textContent = 'Analyse starten';
                document.getElementById('error-message').textContent = 'Verbindungsfehler: ' + err;
                document.getElementById('error-container').style.display = 'block';
            });
        });
    }
});


/**
 * Switch scenario by navigating to the analysis page with new scenario parameter.
 */
function switchScenario(scenario) {
    window.location.href = '.?command=analysis&scenario=' + scenario;
}
