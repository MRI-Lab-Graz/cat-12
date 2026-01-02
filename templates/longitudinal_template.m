
% =============================================================
% MRI-Lab Graz
% Karl Koschutnig
% karl.koschutnig@uni-graz.at
% GitHub repo: https://github.com/MRI-Lab-Graz/cat-12
% =============================================================

% CAT12 Longitudinal Processing Template
% This template is used to generate subject-specific processing scripts
%
% Template variables (replaced by Python script):
% SUBJECT_ID - Subject identifier
% T1W_FILES - Cell array of T1w file paths
% OUTPUT_DIR - Output directory path
% LONGITUDINAL - Boolean for longitudinal processing
% SURFACE_PROCESSING - Boolean for surface processing
% VOLUME_PROCESSING - Boolean for volume processing
% QUALITY_CHECK - Boolean for quality assessment

%% Initialize SPM and CAT12
fprintf('Initializing SPM and CAT12...\n');
addpath(genpath(spm('dir')));
spm_jobman('initcfg');

%% Subject Information
subject_id = '{SUBJECT_ID}';
fprintf('Processing subject: %s\n', subject_id);

%% Input Files
files = {T1W_FILES};
fprintf('Input files:\n');
for i = 1:length(files)
    fprintf('  %d: %s\n', i, files{i});
end

%% Output Directory
output_dir = '{OUTPUT_DIR}';
if ~exist(output_dir, 'dir')
    fprintf('Creating output directory: %s\n', output_dir);
    mkdir(output_dir);
end

%% Processing Configuration
longitudinal_mode = {LONGITUDINAL};
surface_processing = {SURFACE_PROCESSING};
volume_processing = {VOLUME_PROCESSING};
quality_check = {QUALITY_CHECK};

fprintf('Configuration:\n');
fprintf('  Longitudinal mode: %s\n', mat2str(longitudinal_mode));
fprintf('  Surface processing: %s\n', mat2str(surface_processing));
fprintf('  Volume processing: %s\n', mat2str(volume_processing));
fprintf('  Quality check: %s\n', mat2str(quality_check));

%% CAT12 Batch Configuration
clear matlabbatch;

if longitudinal_mode && length(files) > 1
    %% Longitudinal Processing
    fprintf('Setting up longitudinal processing...\n');
    
    % Main longitudinal job
    matlabbatch{1}.spm.tools.cat.long.datalong.subjects = struct();
    matlabbatch{1}.spm.tools.cat.long.datalong.subjects.mov = files;
    matlabbatch{1}.spm.tools.cat.long.datalong.subjects.timepoints = 1:length(files);
    
    % Template and registration options
    matlabbatch{1}.spm.tools.cat.long.opts.tpm = {fullfile(spm('dir'),'tpm','TPM.nii')};
    matlabbatch{1}.spm.tools.cat.long.opts.affreg = 'mni';
    matlabbatch{1}.spm.tools.cat.long.opts.biasstr = 0.5;
    matlabbatch{1}.spm.tools.cat.long.opts.accstr = 0.5;
    
    % Shooting template
    matlabbatch{1}.spm.tools.cat.long.opts.regstr = 0;
    matlabbatch{1}.spm.tools.cat.long.opts.regmethod = 'shooting';
    
    % Surface processing options
    if surface_processing
        matlabbatch{1}.spm.tools.cat.long.surface.pbtres = 0.5;
        matlabbatch{1}.spm.tools.cat.long.surface.pbtmethod = 'pbt2x';
        matlabbatch{1}.spm.tools.cat.long.surface.SRP = 22;
        matlabbatch{1}.spm.tools.cat.long.surface.reduce_mesh = 1;
        matlabbatch{1}.spm.tools.cat.long.surface.vdist = 2;
        matlabbatch{1}.spm.tools.cat.long.surface.scale_cortex = 0.7;
        matlabbatch{1}.spm.tools.cat.long.surface.add_parahipp = 0.1;
        matlabbatch{1}.spm.tools.cat.long.surface.close_parahipp = 0;
    else
        % Disable surface processing
        matlabbatch{1}.spm.tools.cat.long.surface = struct();
    end

    % Explicitly enable/disable surface outputs
    if surface_processing
        matlabbatch{1}.spm.tools.cat.long.output.surface = 1;
    else
        matlabbatch{1}.spm.tools.cat.long.output.surface = 0;
    end
    
    % Volume processing options
    if volume_processing
        % ROI atlases
        matlabbatch{1}.spm.tools.cat.long.output.ROImenu.atlases.neuromorphometrics = 1;
        matlabbatch{1}.spm.tools.cat.long.output.ROImenu.atlases.lpba40 = 1;
        matlabbatch{1}.spm.tools.cat.long.output.ROImenu.atlases.cobra = 1;
        matlabbatch{1}.spm.tools.cat.long.output.ROImenu.atlases.hammers = 1;
        matlabbatch{1}.spm.tools.cat.long.output.ROImenu.atlases.ownatlas = {''};
        
        % Grey Matter output
        matlabbatch{1}.spm.tools.cat.long.output.GM.native = 0;
        matlabbatch{1}.spm.tools.cat.long.output.GM.mod = 1;
        matlabbatch{1}.spm.tools.cat.long.output.GM.dartel = 0;
        
        % White Matter output
        matlabbatch{1}.spm.tools.cat.long.output.WM.native = 0;
        matlabbatch{1}.spm.tools.cat.long.output.WM.mod = 1;
        matlabbatch{1}.spm.tools.cat.long.output.WM.dartel = 0;
        
        % CSF output
        matlabbatch{1}.spm.tools.cat.long.output.CSF.native = 0;
        matlabbatch{1}.spm.tools.cat.long.output.CSF.mod = 0;
        matlabbatch{1}.spm.tools.cat.long.output.CSF.dartel = 0;
        
        % Other outputs
        matlabbatch{1}.spm.tools.cat.long.output.ct.native = 0;
        matlabbatch{1}.spm.tools.cat.long.output.ct.warped = 0;
        matlabbatch{1}.spm.tools.cat.long.output.ct.dartel = 0;
        
        matlabbatch{1}.spm.tools.cat.long.output.pp.native = 0;
        matlabbatch{1}.spm.tools.cat.long.output.pp.warped = 0;
        matlabbatch{1}.spm.tools.cat.long.output.pp.dartel = 0;
        
        matlabbatch{1}.spm.tools.cat.long.output.WMH.native = 0;
        matlabbatch{1}.spm.tools.cat.long.output.WMH.warped = 0;
        matlabbatch{1}.spm.tools.cat.long.output.WMH.mod = 0;
        matlabbatch{1}.spm.tools.cat.long.output.WMH.dartel = 0;
        
        matlabbatch{1}.spm.tools.cat.long.output.SL.native = 0;
        matlabbatch{1}.spm.tools.cat.long.output.SL.warped = 0;
        matlabbatch{1}.spm.tools.cat.long.output.SL.mod = 0;
        matlabbatch{1}.spm.tools.cat.long.output.SL.dartel = 0;
        
        % Jacobian determinant
        matlabbatch{1}.spm.tools.cat.long.output.jacobianwarped = 0;
        
        % Deformation fields
        matlabbatch{1}.spm.tools.cat.long.output.warps = [1 1];
    end
    
    % Longitudinal model and options
    matlabbatch{1}.spm.tools.cat.long.longmodel = 1;
    matlabbatch{1}.spm.tools.cat.long.avgLASWM = 1;
    matlabbatch{1}.spm.tools.cat.long.delete_temp = 1;
    
else
    %% Cross-sectional Processing
    fprintf('Setting up cross-sectional processing...\n');
    
    % Standard CAT12 segmentation
    matlabbatch{1}.spm.tools.cat.estwrite.data = files;
    
    % Tissue probability maps and registration
    matlabbatch{1}.spm.tools.cat.estwrite.opts.tpm = {fullfile(spm('dir'),'tpm','TPM.nii')};
    matlabbatch{1}.spm.tools.cat.estwrite.opts.affreg = 'mni';
    matlabbatch{1}.spm.tools.cat.estwrite.opts.biasstr = 0.5;
    matlabbatch{1}.spm.tools.cat.estwrite.opts.accstr = 0.5;
    
    % Surface processing
    if surface_processing
        matlabbatch{1}.spm.tools.cat.estwrite.surface.pbtres = 0.5;
        matlabbatch{1}.spm.tools.cat.estwrite.surface.pbtmethod = 'pbt2x';
        matlabbatch{1}.spm.tools.cat.estwrite.surface.SRP = 22;
        matlabbatch{1}.spm.tools.cat.estwrite.surface.reduce_mesh = 1;
        matlabbatch{1}.spm.tools.cat.estwrite.surface.vdist = 2;
        matlabbatch{1}.spm.tools.cat.estwrite.surface.scale_cortex = 0.7;
        matlabbatch{1}.spm.tools.cat.estwrite.surface.add_parahipp = 0.1;
        matlabbatch{1}.spm.tools.cat.estwrite.surface.close_parahipp = 0;
    else
        matlabbatch{1}.spm.tools.cat.estwrite.surface = struct();
    end

    % Explicitly enable/disable surface outputs
    if surface_processing
        matlabbatch{1}.spm.tools.cat.estwrite.output.surface = 1;
    else
        matlabbatch{1}.spm.tools.cat.estwrite.output.surface = 0;
    end
    
    % Volume outputs
    if volume_processing
        % ROI processing
        matlabbatch{1}.spm.tools.cat.estwrite.output.ROImenu.atlases.neuromorphometrics = 1;
        matlabbatch{1}.spm.tools.cat.estwrite.output.ROImenu.atlases.lpba40 = 1;
        matlabbatch{1}.spm.tools.cat.estwrite.output.ROImenu.atlases.cobra = 1;
        matlabbatch{1}.spm.tools.cat.estwrite.output.ROImenu.atlases.hammers = 1;
        
        % Grey Matter
        matlabbatch{1}.spm.tools.cat.estwrite.output.GM.native = 0;
        matlabbatch{1}.spm.tools.cat.estwrite.output.GM.mod = 1;
        matlabbatch{1}.spm.tools.cat.estwrite.output.GM.dartel = 0;
        
        % White Matter
        matlabbatch{1}.spm.tools.cat.estwrite.output.WM.native = 0;
        matlabbatch{1}.spm.tools.cat.estwrite.output.WM.mod = 1;
        matlabbatch{1}.spm.tools.cat.estwrite.output.WM.dartel = 0;
        
        % CSF
        matlabbatch{1}.spm.tools.cat.estwrite.output.CSF.native = 0;
        matlabbatch{1}.spm.tools.cat.estwrite.output.CSF.mod = 0;
        matlabbatch{1}.spm.tools.cat.estwrite.output.CSF.dartel = 0;
        
        % Bias corrected image
        matlabbatch{1}.spm.tools.cat.estwrite.output.bias.warped = 1;
        
        % Deformation fields
        matlabbatch{1}.spm.tools.cat.estwrite.output.warps = [1 1];
    end
end

%% Execute Processing
fprintf('Starting CAT12 processing...\n');
tic;

try
    spm_jobman('run', matlabbatch);
    
    processing_time = toc;
    fprintf('CAT12 processing completed successfully in %.2f seconds (%.2f minutes)\n', ...
            processing_time, processing_time/60);
    
    % Save processing information
    processing_info = struct();
    processing_info.subject_id = subject_id;
    processing_info.files = files;
    processing_info.output_dir = output_dir;
    processing_info.longitudinal_mode = longitudinal_mode;
    processing_info.surface_processing = surface_processing;
    processing_info.volume_processing = volume_processing;
    processing_info.processing_time = processing_time;
    processing_info.completion_time = datestr(now);
    processing_info.matlabbatch = matlabbatch;
    
    info_file = fullfile(output_dir, 'processing_info.mat');
    save(info_file, 'processing_info');
    fprintf('Processing information saved to: %s\n', info_file);
    
    % Create success marker
    success_file = fullfile(output_dir, 'CAT12_PROCESSING_COMPLETED.txt');
    fid = fopen(success_file, 'w');
    if fid > 0
        fprintf(fid, 'CAT12 processing completed successfully\n');
        fprintf(fid, 'Subject: %s\n', subject_id);
        fprintf(fid, 'Completion time: %s\n', datestr(now));
        fprintf(fid, 'Processing time: %.2f seconds\n', processing_time);
        fclose(fid);
    end
    
    fprintf('Success marker created: %s\n', success_file);
    
catch ME
    processing_time = toc;
    fprintf('Error during CAT12 processing after %.2f seconds: %s\n', ...
            processing_time, ME.message);
    
    % Save error information
    error_info = struct();
    error_info.subject_id = subject_id;
    error_info.files = files;
    error_info.output_dir = output_dir;
    error_info.error_message = ME.message;
    error_info.error_stack = ME.stack;
    error_info.processing_time = processing_time;
    error_info.error_time = datestr(now);
    error_info.matlabbatch = matlabbatch;
    
    error_file = fullfile(output_dir, 'processing_error.mat');
    save(error_file, 'error_info');
    fprintf('Error information saved to: %s\n', error_file);
    
    % Create error marker
    error_marker = fullfile(output_dir, 'CAT12_PROCESSING_FAILED.txt');
    fid = fopen(error_marker, 'w');
    if fid > 0
        fprintf(fid, 'CAT12 processing failed\n');
        fprintf(fid, 'Subject: %s\n', subject_id);
        fprintf(fid, 'Error time: %s\n', datestr(now));
        fprintf(fid, 'Error message: %s\n', ME.message);
        fclose(fid);
    end
    
    % Rethrow error for calling script
    rethrow(ME);
end

%% Quality Check
if quality_check
    fprintf('Running quality assessment...\n');
    try
        % Look for CAT12 quality report
        report_dir = fullfile(output_dir, 'report');
        if exist(report_dir, 'dir')
            xml_files = dir(fullfile(report_dir, 'cat_*.xml'));
            if ~isempty(xml_files)
                fprintf('Quality report found: %s\n', ...
                        fullfile(report_dir, xml_files(1).name));
            else
                fprintf('Warning: No quality report XML files found\n');
            end
        else
            fprintf('Warning: No report directory found\n');
        end
    catch QA_ME
        fprintf('Warning: Quality assessment failed: %s\n', QA_ME.message);
    end
end

fprintf('Script execution completed for subject: %s\n', subject_id);
fprintf('Output directory: %s\n', output_dir);

% Exit MATLAB (important for standalone execution)
exit;