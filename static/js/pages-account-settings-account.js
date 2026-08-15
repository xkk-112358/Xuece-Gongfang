/**
 * Account Settings - Account
 */

'use strict';

document.addEventListener('DOMContentLoaded', function (e) {
  (function () {
    // Update/reset user image of account page
    let accountUserImage = document.getElementById('uploadedAvatar');
    const fileInput = document.querySelector('.account-file-input'),
      resetFileInput = document.querySelector('.account-image-reset');

    if (accountUserImage) {
      const resetImage = accountUserImage.src;
      fileInput.onchange = () => {
        if (fileInput.files[0]) {
          accountUserImage.src = window.URL.createObjectURL(fileInput.files[0]);
          // 上传头像
          const formData = new FormData();
          formData.append('avatar', fileInput.files[0]);
          
          fetch('/my/upload_avatar/', {
            method: 'POST',
            headers: {
              'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
            },
            body: formData
          })
          .then(response => response.json())
          .then(data => {
            if (!data.success) {
              alert('头像上传失败：' + data.message);
              accountUserImage.src = resetImage;
            }
          })
          .catch(error => {
            console.error('Error:', error);
            alert('头像上传失败');
            accountUserImage.src = resetImage;
          });
        }
      };
      resetFileInput.onclick = () => {
        fileInput.value = '';
        accountUserImage.src = resetImage;
      };
    }

    // 初始化学校选择下拉框
    const schoolSelect = document.querySelector('#school');
    if (schoolSelect && typeof $ !== 'undefined' && $.fn.select2) {
      $(schoolSelect).select2({
        theme: 'bootstrap-5',
        language: {
          inputTooShort: function(args) {
            return '请输入至少 1 个字符';
          },
          searching: function() {
            return '搜索中...';
          },
          noResults: function() {
            return '未找到匹配的学校';
          },
          loadingMore: function() {
            return '加载更多结果...';
          },
          errorLoading: function() {
            return '无法加载结果';
          }
        },
        placeholder: '请输入学校名称搜索',
        allowClear: false,
        minimumInputLength: 1,
        ajax: {
          url: '/api/search_universities/',
          dataType: 'json',
          delay: 250,
          data: function (params) {
            return {
              q: params.term
            };
          },
          processResults: function (data) {
            return {
              results: data
            };
          },
          cache: true
        },
        templateSelection: function (data) {
          return data.text || data.id || '';
        }
      });
    }

    // 编辑和保存功能
    const btnEdit = document.getElementById('btnEdit');
    const btnSave = document.getElementById('btnSave');
    const firstNameInput = document.getElementById('firstName');
    const schoolSelectEl = document.getElementById('school');
    const aiModelSelect = document.getElementById('ai_model');
    const birthdayInput = document.getElementById('birthday');
    
    // 初始化锁定生日字段
    if (birthdayInput) {
      birthdayInput.disabled = true;
    }

    // 编辑按钮点击事件
    btnEdit.addEventListener('click', function() {
      firstNameInput.removeAttribute('readonly');
      schoolSelectEl.removeAttribute('disabled');
      if (aiModelSelect) aiModelSelect.removeAttribute('disabled');
      if (birthdayInput) birthdayInput.disabled = false;
      
      if (typeof $ !== 'undefined' && $.fn.select2 && schoolSelectEl) {
        $(schoolSelectEl).select2('destroy');
        $(schoolSelectEl).select2({
          theme: 'bootstrap-5',
          language: {
            inputTooShort: function(args) {
              return '请输入至少 1 个字符';
            },
            searching: function() {
              return '搜索中...';
            },
            noResults: function() {
              return '未找到匹配的学校';
            },
            loadingMore: function() {
              return '加载更多结果...';
            },
            errorLoading: function() {
              return '无法加载结果';
            }
          },
          placeholder: '请输入学校名称搜索',
          allowClear: false,
          minimumInputLength: 1,
          ajax: {
            url: '/api/search_universities/',
            dataType: 'json',
            delay: 250,
            data: function (params) {
              return {
                q: params.term
              };
            },
            processResults: function (data) {
              return {
                results: data
              };
            },
            cache: true
          },
          templateSelection: function (data) {
            return data.text || data.id || '';
          }
        });
      }

      btnEdit.style.display = 'none';
      btnSave.removeAttribute('disabled');
    });

    // 保存按钮点击事件
    btnSave.addEventListener('click', function() {
      const formData = new FormData();
      formData.append('firstName', firstNameInput.value);
      formData.append('school', schoolSelectEl.value);
      formData.append('ai_model', aiModelSelect ? aiModelSelect.value : '');
      formData.append('birthday', birthdayInput.value);

      fetch('/save_profile/', {
        method: 'POST',
        headers: {
          'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
        },
        body: formData
      })
      .then(response => response.json())
      .then(data => {
        if (data.success) {
          alert('保存成功');
          firstNameInput.setAttribute('readonly', '');
          schoolSelectEl.setAttribute('disabled', '');
          if (aiModelSelect) aiModelSelect.setAttribute('disabled', '');
          if (birthdayInput) birthdayInput.disabled = true;
          
          if (typeof $ !== 'undefined' && $.fn.select2 && schoolSelectEl) {
            $(schoolSelectEl).select2('destroy');
          }

          btnSave.setAttribute('disabled', '');
          btnEdit.style.display = 'inline-block';

          // 更新年龄显示
          var ageDisplay = document.getElementById('age-display');
          if (ageDisplay) {
            if (birthdayInput && birthdayInput.value) {
              var birthdayVal = birthdayInput.value;
              var birthDate = new Date(birthdayVal);
              var today = new Date();
              var age = today.getFullYear() - birthDate.getFullYear();
              var m = today.getMonth() - birthDate.getMonth();
              if (m < 0 || (m === 0 && today.getDate() < birthDate.getDate())) {
                age--;
              }
              ageDisplay.textContent = age + '岁';
              ageDisplay.classList.remove('d-none');
            } else {
              ageDisplay.classList.add('d-none');
            }
          }
        } else {
          alert('保存失败：' + data.message);
        }
      })
      .catch(error => {
        console.error('Error:', error);
        alert('保存失败');
      });
    });

    // 文件管理相关操作
    document.addEventListener('click', function(e) {
      // 删除文件
      const deleteBtn = e.target.closest('.delete-upload');
      if (deleteBtn) {
        if (!confirm('确定删除此文件？')) {
          return;
        }
        const uploadId = deleteBtn.dataset.uploadId;
        
        fetch(`/delete_upload/${uploadId}/`, {
          method: 'POST',
          headers: {
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
          }
        })
        .then(response => response.json())
        .then(data => {
          if (data.success) {
            alert('文件删除成功');
            const row = deleteBtn.closest('tr');
            if (row) {
              row.remove();
            }
          } else {
            alert('删除失败：' + data.message);
          }
        })
        .catch(error => {
          console.error('Error:', error);
          alert('删除失败');
        });
        return;
      }
      
      // 共享状态切换
      const shareBtn = e.target.closest('.toggle-share');
      if (shareBtn) {
        const uploadId = shareBtn.dataset.uploadId;
        
        fetch(`/toggle_share/${uploadId}/`, {
          method: 'POST',
          headers: {
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
          }
        })
        .then(response => response.json())
        .then(data => {
          if (data.success) {
            if (data.is_shared) {
              shareBtn.textContent = '是';
              shareBtn.classList.remove('btn-secondary');
              shareBtn.classList.add('btn-success');
            } else {
              shareBtn.textContent = '否';
              shareBtn.classList.remove('btn-success');
              shareBtn.classList.add('btn-secondary');
            }
          } else {
            alert('操作失败：' + data.message);
          }
        })
        .catch(error => {
          console.error('Error:', error);
          alert('操作失败');
        });
        return;
      }
      
      // 编辑按钮点击
      const editBtn = e.target.closest('.edit-upload');
      if (editBtn) {
        const uploadId = editBtn.dataset.uploadId;
        const fileName = editBtn.dataset.fileName;
        const description = editBtn.dataset.description;
        const subject = editBtn.dataset.subject || '';
        
        document.getElementById('editUploadId').value = uploadId;
        document.getElementById('editFileName').value = fileName;
        document.getElementById('editDescription').value = description;
        document.getElementById('editSubject').value = subject;
        
        const modal = new bootstrap.Modal(document.getElementById('editUploadModal'));
        modal.show();
        return;
      }
      
      // 打开题库 - 直接跳转到独立页面
      const openBankBtn = e.target.closest('.open-question-bank');
      if (openBankBtn) {
        const uploadId = openBankBtn.dataset.uploadId;
        window.location.href = '/open_question_bank/' + uploadId + '/';
        return;
      }
      
      // 收藏切换（题目、帖子）
      const favoriteStar = e.target.closest('.favorite-star');
      if (favoriteStar && !favoriteStar.classList.contains('file-favorite-star')) {
        const questionId = favoriteStar.dataset.questionId;
        const postId = favoriteStar.dataset.postId;
        const uploadId = favoriteStar.dataset.uploadId;
        
        const formData = new FormData();
        if (questionId) {
          formData.append('question_id', questionId);
        } else if (postId) {
          formData.append('post_id', postId);
        } else if (uploadId) {
          formData.append('upload_id', uploadId);
        }
        
        let url = '';
        if (questionId) {
          url = '/toggle_favorite/';
        } else if (postId) {
          url = '/toggle_post_favorite/';
        } else if (uploadId) {
          url = '/toggle_file_favorite/';
        }
        
        if (url) {
          fetch(url, {
            method: 'POST',
            headers: {
              'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
            },
            body: formData
          })
          .then(response => response.json())
          .then(data => {
            if (data.success) {
              if (data.is_favorited) {
                favoriteStar.classList.remove('ri-star-line');
                favoriteStar.classList.add('ri-star-fill', 'text-warning');
              } else {
                favoriteStar.classList.remove('ri-star-fill', 'text-warning');
                favoriteStar.classList.add('ri-star-line');
              }
              if (uploadId) {
                var favTab = document.querySelector('#tab-content-favorites');
                if (favTab && favTab.classList.contains('active')) {
                  refreshFavorites();
                }
              }
            }
          })
          .catch(error => {
            console.error('Error:', error);
          });
        }
        return;
      }
      
      // 文件收藏切换
      const fileFavoriteStar = e.target.closest('.file-favorite-star');
      if (fileFavoriteStar) {
        const uploadId = fileFavoriteStar.dataset.uploadId;
        const formData = new FormData();
        formData.append('upload_id', uploadId);
        
        fetch('/toggle_file_favorite/', {
          method: 'POST',
          headers: {
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
          },
          body: formData
        })
        .then(response => response.json())
        .then(data => {
          if (data.success) {
            if (data.is_favorited) {
              fileFavoriteStar.classList.remove('ri-star-line');
              fileFavoriteStar.classList.add('ri-star-fill', 'text-warning');
            } else {
              fileFavoriteStar.classList.remove('ri-star-fill', 'text-warning');
              fileFavoriteStar.classList.add('ri-star-line');
            }
            var favTab = document.querySelector('#tab-content-favorites');
            if (favTab && favTab.classList.contains('active')) {
              refreshFavorites();
            }
          }
        })
        .catch(error => {
          console.error('Error:', error);
        });
        return;
      }
      
      // 返回按钮
      const backBtn = e.target.closest('#backToUploads');
      if (backBtn) {
        e.preventDefault();
        const modal = bootstrap.Modal.getInstance(document.getElementById('questionBankModal'));
        if (modal) {
          modal.hide();
        }
        return;
      }
      
      // 关注用户
      const followBtn = e.target.closest('.follow-btn');
      if (followBtn) {
        e.preventDefault();
        const userId = followBtn.dataset.userId;
        
        fetch('/toggle_follow/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
          },
          body: 'target_user_id=' + userId
        })
        .then(response => response.json())
        .then(data => {
          if (data.success) {
            followBtn.classList.remove('btn-outline-primary');
            followBtn.classList.add('btn-outline-danger');
            followBtn.textContent = '取消关注';
            followBtn.classList.remove('follow-btn');
            followBtn.classList.add('unfollow-btn');
            
            updateFollowCounts(data.following_count, data.follower_count);
          } else {
            alert('关注失败：' + data.message);
          }
        })
        .catch(error => {
          console.error('Error:', error);
          alert('关注失败');
        });
        return;
      }
      
      // 取消关注
      const unfollowBtn = e.target.closest('.unfollow-btn');
      if (unfollowBtn) {
        e.preventDefault();
        if (confirm('确定要取消关注吗？')) {
          const userId = unfollowBtn.dataset.userId;
          
          fetch('/toggle_follow/', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/x-www-form-urlencoded',
              'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
            },
            body: 'target_user_id=' + userId
          })
          .then(response => response.json())
          .then(data => {
            if (data.success) {
              unfollowBtn.classList.remove('btn-outline-danger');
              unfollowBtn.classList.add('btn-outline-primary');
              unfollowBtn.textContent = '关注';
              unfollowBtn.classList.remove('unfollow-btn');
              unfollowBtn.classList.add('follow-btn');
              
              updateFollowCounts(data.following_count, data.follower_count);
            } else {
              alert('取消关注失败：' + data.message);
            }
          })
          .catch(error => {
            console.error('Error:', error);
            alert('取消关注失败');
          });
        }
        return;
      }
      
      // 编辑题目按钮
      const editQuestionBtn = e.target.closest('.edit-question-btn');
      if (editQuestionBtn) {
        const questionId = editQuestionBtn.dataset.questionId;
        const container = document.querySelector('[data-question-id="' + questionId + '"]');
        
        container.querySelector('.question-content-view').classList.add('d-none');
        container.querySelector('.question-content-edit').classList.remove('d-none');
        container.querySelector('.question-answer-view').classList.add('d-none');
        container.querySelector('.question-answer-edit').classList.remove('d-none');
        container.querySelector('.edit-question-btn').classList.add('d-none');
        container.querySelector('.save-question-btn').classList.remove('d-none');
        container.querySelector('.cancel-edit-btn').classList.remove('d-none');
        return;
      }
      
      // 取消编辑按钮
      const cancelEditBtn = e.target.closest('.cancel-edit-btn');
      if (cancelEditBtn) {
        const questionId = cancelEditBtn.dataset.questionId;
        const container = document.querySelector('[data-question-id="' + questionId + '"]');
        
        container.querySelector('.question-content-view').classList.remove('d-none');
        container.querySelector('.question-content-edit').classList.add('d-none');
        container.querySelector('.question-answer-view').classList.remove('d-none');
        container.querySelector('.question-answer-edit').classList.add('d-none');
        container.querySelector('.edit-question-btn').classList.remove('d-none');
        container.querySelector('.save-question-btn').classList.add('d-none');
        container.querySelector('.cancel-edit-btn').classList.add('d-none');
        return;
      }
      
      // 保存题目按钮
      const saveQuestionBtn = e.target.closest('.save-question-btn');
      if (saveQuestionBtn) {
        const questionId = saveQuestionBtn.dataset.questionId;
        const container = document.querySelector('[data-question-id="' + questionId + '"]');
        
        const content = container.querySelector('.question-content-textarea').value;
        const answer = container.querySelector('.question-answer-textarea').value;
        
        const formData = new FormData();
        formData.append('question_id', questionId);
        formData.append('content', content);
        formData.append('answer', answer);
        formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);
        
        fetch('/edit_question/', {
          method: 'POST',
          body: formData
        })
        .then(response => response.json())
        .then(data => {
          if (data.success) {
            alert('保存成功');
            const modal = bootstrap.Modal.getInstance(document.getElementById('questionBankModal'));
            if (modal) {
              modal.hide();
            }
            // 手动移除模态框背景遮罩，防止残留
            setTimeout(function() {
              const backdrop = document.querySelector('.modal-backdrop');
              if (backdrop) {
                backdrop.remove();
              }
              document.body.classList.remove('modal-open');
            }, 100);
          } else {
            alert('保存失败: ' + data.message);
          }
        })
        .catch(error => {
          console.error('Error:', error);
          alert('保存失败');
        });
        return;
      }
      
    });

    // 加入题单对话框（静态JS版本）
    window.showAddToListDialogStatic = function(questionIds) {
      fetch('/get_question_lists/')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (!data.success) { alert('获取题单失败'); return; }
        var lists = data.lists;
        var html = '<div class="mb-3"><label class="form-label">选择题单</label><select class="form-select" id="sDialogSelectList">';
        if (lists.length === 0) {
          html += '<option value="">暂无题单，请先创建</option>';
        } else {
          lists.forEach(function(l) {
            html += '<option value="' + l.id + '">' + l.title + '（' + l.count + '题）</option>';
          });
        }
        html += '</select></div><div class="mb-3"><label class="form-label">或新建题单</label><input type="text" class="form-control" id="sDialogNewListName" placeholder="输入题单名称"></div>';
        
        var modalDiv = document.createElement('div');
        modalDiv.className = 'modal fade';
        modalDiv.innerHTML = '<div class="modal-dialog"><div class="modal-content"><div class="modal-header"><h5 class="modal-title">加入题单</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div><div class="modal-body">' + html + '</div><div class="modal-footer"><button type="button" class="btn btn-primary" id="sDialogConfirmAdd">确定</button></div></div></div>';
        document.body.appendChild(modalDiv);
        var modal = new bootstrap.Modal(modalDiv);
        modal.show();
        modalDiv.addEventListener('hidden.bs.modal', function() { modalDiv.remove(); });
        
        document.getElementById('sDialogConfirmAdd').addEventListener('click', function() {
          var selectedId = document.getElementById('sDialogSelectList').value;
          var newName = document.getElementById('sDialogNewListName').value.trim();
          var csrf = document.querySelector('[name=csrfmiddlewaretoken]');
          csrf = csrf ? csrf.value : '';
          
          function doAdd(listId) {
            fetch('/add_to_question_list/', {
              method: 'POST',
              headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
              body: JSON.stringify({list_id: listId, question_ids: questionIds})
            }).then(function(r) { return r.json(); })
            .then(function(d) {
              if (d.success) { alert('已加入题单（' + d.added + '题）！'); modal.hide(); }
              else { alert(d.message); }
            });
          }
          
          if (newName) {
            fetch('/create_question_list/', {
              method: 'POST',
              headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
              body: JSON.stringify({title: newName, description: ''})
            }).then(function(r) { return r.json(); })
            .then(function(d) {
              if (d.success) { doAdd(d.question_list.id); }
              else { alert(d.message); }
            });
          } else if (selectedId) {
            doAdd(parseInt(selectedId));
          } else {
            alert('请选择或创建题单');
          }
        });
      });
    };

    // 选择头像函数
    window.selectAvatar = function(avatarName) {
      const formData = new FormData();
      formData.append('avatar_name', avatarName);
      
      fetch('/my/select_default_avatar/', {
        method: 'POST',
        headers: {
          'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
        },
        body: formData
      })
      .then(response => response.json())
      .then(data => {
        if (data.success) {
          const modal = bootstrap.Modal.getInstance(document.getElementById('avatarModal'));
          modal.hide();
          const avatarUrl = '/static/pictures/头像/' + avatarName;
          document.getElementById('uploadedAvatar').src = avatarUrl;
          alert('头像设置成功');
        } else {
          alert('头像设置失败：' + data.message);
        }
      })
      .catch(error => {
        console.error('Error:', error);
        alert('头像设置失败');
      });
    };

    // 头像选择点击事件 - 使用事件委托
    document.addEventListener('click', function(e) {
      if (e.target && e.target.classList.contains('avatar-option')) {
        var avatarPath = e.target.getAttribute('data-avatar');
        var avatarName = avatarPath.split('/').pop();
        window.selectAvatar(avatarName);
      }
    });
    
    // 保存编辑
    document.getElementById('btnSaveEdit').addEventListener('click', function() {
      const uploadId = document.getElementById('editUploadId').value;
      const newFileName = document.getElementById('editFileName').value.trim();
      const newDescription = document.getElementById('editDescription').value;
      const newSubject = document.getElementById('editSubject').value.trim();
      
      // 验证必填项
      if (!newFileName) {
        alert('请填写文件名');
        document.getElementById('editFileName').focus();
        return;
      }
      
      if (!newSubject) {
        alert('请填写学科');
        document.getElementById('editSubject').focus();
        return;
      }
      
      const formData = new FormData();
      formData.append('upload_id', uploadId);
      formData.append('file_name', newFileName);
      formData.append('description', newDescription);
      formData.append('subject', newSubject);
      
      fetch('/edit_upload/', {
        method: 'POST',
        headers: {
          'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
        },
        body: formData
      })
      .then(response => response.json())
      .then(data => {
        if (data.success) {
          alert('保存成功');
          window.location.reload();
        } else {
          alert('保存失败：' + data.message);
        }
      })
      .catch(error => {
        console.error('Error:', error);
        alert('保存失败');
      });
    });
    
    // 刷新收藏列表
    window.refreshFavorites = function() {
      const currentTab = document.querySelector('#tab-content-favorites .nav-link.active');
      if (!currentTab) return;
      const tabId = currentTab.id;
      
      fetch(window.location.pathname + window.location.search, {
        method: 'GET',
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      })
      .then(response => response.text())
      .then(html => {
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, 'text/html');
        let newContent = null;
        if (tabId === 'subtab-fav-files') {
          newContent = doc.querySelector('#subtab-content-fav-files');
        } else if (tabId === 'subtab-fav-questions') {
          newContent = doc.querySelector('#subtab-content-fav-questions');
        } else if (tabId === 'subtab-fav-posts') {
          newContent = doc.querySelector('#subtab-content-fav-posts');
        }
        if (newContent) {
          document.getElementById(newContent.id).innerHTML = newContent.innerHTML;
        }
      })
      .catch(function() {
        location.reload();
      });
    };
  })();
});

// 更新关注和粉丝数
function updateFollowCounts(followingCount, followerCount) {
  var followingEl = document.querySelector('.following-count');
  var followerEl = document.querySelector('.follower-count');
  
  if (followingEl) {
    followingEl.textContent = followingCount;
  }
  if (followerEl) {
    followerEl.textContent = followerCount;
  }
}
