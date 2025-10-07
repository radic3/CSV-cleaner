// Upload page JavaScript for drag and drop functionality
document.addEventListener('DOMContentLoaded', function() {
  const dropM = document.getElementById('drop-multi');
  const inputsM = document.getElementById('files');
  const submitM = document.getElementById('submit-multi');
  const namesM = document.getElementById('filenames');
  
  if (dropM && inputsM && submitM && namesM) {
    dropM.addEventListener('click', () => inputsM.click());
    dropM.addEventListener('dragover', (e) => { 
      e.preventDefault(); 
      dropM.classList.add('dragover'); 
    });
    dropM.addEventListener('dragleave', () => dropM.classList.remove('dragover'));
    dropM.addEventListener('drop', (e) => {
      e.preventDefault();
      dropM.classList.remove('dragover');
      if (e.dataTransfer.files && e.dataTransfer.files.length) {
        inputsM.files = e.dataTransfer.files;
        namesM.textContent = Array.from(e.dataTransfer.files).map(f => f.name).join(', ');
        submitM.disabled = false;
      }
    });
    inputsM.addEventListener('change', () => {
      if (inputsM.files && inputsM.files.length) {
        namesM.textContent = Array.from(inputsM.files).map(f => f.name).join(', ');
        submitM.disabled = false;
      }
    });
  }
});
