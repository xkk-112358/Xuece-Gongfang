const texts = [
          "欢迎来到学测工坊",
          "Word/pdf题库一键导入",
          "智能刷题 | 自动判分",
          "轻松学习，高效备考"
        ];

        const typingSpeed = 80;
        const deletingSpeed = 50;
        const pauseTime = 2000;

        const typeElement = document.getElementById("typeText");
        let textIndex = 0;
        let charIndex = 0;
        let isDeleting = false;

        function typeEffect() {
          const currentText = texts[textIndex];

          if (!isDeleting) {
            typeElement.textContent = currentText.substring(0, charIndex + 1);
            charIndex++;
          } else {
            typeElement.textContent = currentText.substring(0, charIndex - 1);
            charIndex--;
          }

          let speed = isDeleting ? deletingSpeed : typingSpeed;

          if (!isDeleting && charIndex === currentText.length) {
            speed = pauseTime;
            isDeleting = true;
          } else if (isDeleting && charIndex === 0) {
            isDeleting = false;
            textIndex = (textIndex + 1) % texts.length;
          }

          setTimeout(typeEffect, speed);
        }

        typeEffect();