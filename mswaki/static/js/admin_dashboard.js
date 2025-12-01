document.addEventListener("DOMContentLoaded", function() {
  // Check if the chart element exists
  const chartEl = document.getElementById("revenue-chart");
  if (!chartEl) return;

  // Initialize the revenue chart
  const ctx = chartEl.getContext("2d");
  
  // Get data from the template
  const revenueData = {
    labels: JSON.parse('{{ stats.revenue_labels | tojson | safe }}'),
    data: JSON.parse('{{ stats.revenue_data | tojson | safe }}')
  };

  // Create the chart
  const revenueChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: revenueData.labels,
      datasets: [{
        label: 'Revenue KES',
        data: revenueData.data,
        fill: true,
        backgroundColor: 'rgba(59, 130, 246, 0.2)',
        borderColor: 'rgba(59, 130, 246, 1)',
        tension: 0.4,
        pointBackgroundColor: 'rgba(59, 130, 246, 1)',
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { 
          display: true,
          position: 'top'
        },
        tooltip: { 
          mode: 'index', 
          intersect: false 
        }
      },
      scales: {
        x: { 
          title: { 
            display: true, 
            text: 'Month' 
          } 
        },
        y: { 
          title: { 
            display: true, 
            text: 'Revenue (KES)' 
          },
          beginAtZero: true 
        }
      }
    }
  });

  // Export CSV functionality
  const exportBtn = document.getElementById("export-csv");
  if (exportBtn) {
    exportBtn.addEventListener("click", function(e) {
      e.preventDefault();
      
      const table = document.getElementById("recent-bookings-table");
      if (!table) return;

      let csvContent = "";
      
      // Get headers
      const headers = table.querySelectorAll("thead th");
      let headerRow = [];
      headers.forEach(th => headerRow.push(`"${th.innerText.trim()}"`));
      csvContent += headerRow.join(",") + "\n";

      // Get table rows
      const rows = table.querySelectorAll("tbody tr");
      rows.forEach(row => {
        let rowData = [];
        row.querySelectorAll("td").forEach(td => rowData.push(`"${td.innerText.trim()}"`));
        csvContent += rowData.join(",") + "\n";
      });

      // Download CSV
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.setAttribute("href", url);
      link.setAttribute("download", `bookings_${new Date().toISOString().split('T')[0]}.csv`);
      link.style.visibility = 'hidden';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    });
  }
});
